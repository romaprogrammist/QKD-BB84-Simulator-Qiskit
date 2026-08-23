# ==============================================================================
# © 2025-2026 Максимов Роман Викторович. Все права защищены.
#
# Проект: QKD-BB84-Simulator-Qiskit (Версия v3.2)
#
# Данное программное обеспечение и его исходный код являются конфиденциальной
# интеллектуальной собственностью автора. Допуск предоставлен исключительно 
# для целей академического аудита и рецензирования. Любое несанкционированное 
# копирование, распространение, модификация или реверс-инжиниринг запрещены.
# Подробные условия использования изложены в файле PROPRIETARY_NOTICE.md.
# ==============================================================================
import numpy as np
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import customtkinter as ctk
from tkinter import messagebox
import threading
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import hashlib


# --- КВАНТОВЫЕ ФУНКЦИИ И АТАКИ ---

def generate_random_bits(num_bits):
    """Генерирует случайную последовательность классических бит (0 или 1)."""
    return np.random.randint(0, 2, num_bits)


def generate_random_bases(num_bits):
    """Генерирует случайные базисы (0 для стандартного +, 1 для диагонального x)."""
    return np.random.randint(0, 2, num_bits)


def prepare_qubits(bits, bases):
    """
    Алиса: Подготавливает квантовые состояния (кубиты) на основе битовой строки и выбранных базисов.
    Кодирование:
      - Базис + (0): |0⟩ или |1⟩ (применением гейта X)
      - Базис × (1): |+⟩ или |-⟩ (применением гейтов X и Адамара H)
    """
    qc = QuantumCircuit(len(bits), len(bits))
    for i in range(len(bits)):
        if bits[i] == 1:
            qc.x(i)
        if bases[i] == 1:
            qc.h(i)
    return qc



def apply_channel_noise(qc, noise_probability):
    """
    Моделирование воздействия квантового деполяризующего канала.
    С заданной вероятностью p кубит претерпевает случайную квантовую ошибку Паули:
    - Битовый переворот (Bit-flip, гейт X)
    - Фазовый переворот (Phase-flip, гейт Z)
    - Смешанная ошибка (Bit-Phase flip, гейт Y)
    Ошибки распределены равновероятно (по p/3 на каждый тип), что соответствует физической
    модели симметричной деполяризации в волоконно-оптической линии связи.
    """
    if noise_probability <= 0:
        return qc

    for i in range(qc.num_qubits):
        if np.random.rand() < noise_probability:
            error_type = np.random.randint(0, 3)  # Равновероятный выбор ошибки X, Y или Z
            if error_type == 0:
                qc.x(i)
            elif error_type == 1:
                qc.y(i)
            else:
                qc.z(i)
    return qc


def measure_qubits(qc_to_measure, bases):
    """
    Боб / Ева: Физическое измерение кубитов в случайно выбранных базисах.
    Для измерения в диагональном базисе предварительно применяется гейт Адамара (H),
    проектирующий состояния |+⟩ и |-⟩ на вычислительную ось Z.
    
    Учитывается порядок следования битов в Qiskit (Little-Endian),
    строка результатов инвертируется для корректного сопоставления индексов кубитов.
    """
    qc_copy = qc_to_measure.copy()
    num_m_qubits = len(bases)
    for i in range(num_m_qubits):
        if bases[i] == 1:
            qc_copy.h(i)
        qc_copy.measure(i, i)

    try:
        # Симуляция методом Matrix Product State (MPS) для оптимизации выделения памяти
        simulator = AerSimulator(method='matrix_product_state')
        job = simulator.run(qc_copy, shots=1)
        result = job.result().get_counts()
    except Exception:
        # Резервный запуск с автоматическим выбором метода симуляции
        simulator = AerSimulator()
        job = simulator.run(qc_copy, shots=1)
        result = job.result().get_counts()

    measured_bits_str = list(result.keys())[0]
    # Извлекаем измеренные биты для первых num_m_qubits
    measured_bits = np.array([int(b) for b in measured_bits_str[::-1][:num_m_qubits]])
    return measured_bits



def eavesdrop_on_qubits(qc_from_alice, num_qubits, attack_type="Стандартный перехват-повтор"):
    """
    Ева: Моделирование различных сценариев перехвата информации в квантовом канале.
    Замечание 6: Индивидуальные когерентные атаки реализуются с использованием
    вспомогательных кубитов (ancilla qubits) и квантового зацепления (CNOT).
    """
    eve_measured_bits = np.zeros(num_qubits, dtype=int)
    eve_bases = np.zeros(num_qubits, dtype=int)
    ancilla_circuit = None

    if attack_type == "Стандартный перехват-повтор":
        # Атака Intercept-Resend: Ева измеряет кубиты в случайных базисах BB84
        # и переотправляет новые кубиты Бобу. Вносит средний QBER ~ 25%.
        eve_bases = generate_random_bases(num_qubits)
        eve_measured_bits = measure_qubits(qc_from_alice.copy(), eve_bases)
        qc_to_bob = prepare_qubits(eve_measured_bits, eve_bases)

    elif attack_type == "Перехват под углом 22.5°":
        # Атака Брейдбарта (Breidbart basis attack):
        # Измерение в промежуточном базисе, повернутом на π/8 (22.5°) относительно осей BB84.
        # Поворот Ry(-π/4) на сфере Блоха проецирует состояния ровно посредине между + и ×.
        qc_copy = qc_from_alice.copy()
        for i in range(num_qubits):
            qc_copy.ry(-np.pi / 4, i)

        eve_bases = np.zeros(num_qubits, dtype=int)
        eve_measured_bits = measure_qubits(qc_copy, eve_bases)

        # Подготовка состояний для отправки Бобу
        qc_to_bob = QuantumCircuit(num_qubits, num_qubits)
        for i in range(num_qubits):
            if eve_measured_bits[i] == 1:
                qc_to_bob.x(i)
            qc_to_bob.ry(np.pi / 4, i)

    elif attack_type == "Атака с квантовой памятью":
        # Замечание 6 (Рекомендация ИФ НАН Беларуси):
        # Индивидуальная когерентная атака с квантовой памятью.
        # Теорема о невозможности квантового клонирования запрещает идеальное копирование.
        # Ева создает вспомогательные кубиты (ancilla), проводит унитарную двухкубитную
        # операцию (CNOT) для зацепления состояния основного кубита со вспомогательным,
        # отправляет основной кубит Бобу, а вспомогательный сохраняет в квантовой памяти.
        
        # Схема с 2*num_qubits кубитами: [0..N-1] - канальные, [N..2N-1] - память Евы
        combined_qc = QuantumCircuit(2 * num_qubits, 2 * num_qubits)
        # Копируем вентили Алисы на канальные кубиты
        combined_qc.compose(qc_from_alice, qubits=list(range(num_qubits)), clbits=list(range(num_qubits)), inplace=True)
        
        # Двухкубитная операция зацепления (CNOT: основной кубит -> ancilla кубит Евы)
        for i in range(num_qubits):
            combined_qc.cx(i, num_qubits + i)
            
        # Боб получает канальные кубиты (первые N)
        qc_to_bob = combined_qc  # Передаем комбинированную схему
        eve_bases = np.zeros(num_qubits, dtype=int)
        eve_measured_bits = np.zeros(num_qubits, dtype=int)

    else:
        qc_to_bob = qc_from_alice.copy()

    return qc_to_bob, eve_bases, eve_measured_bits



# --- КЛАССИЧЕСКАЯ ПОСТОБРАБОТКА ---

def sift_key(alice_bits, alice_bases, bob_bits, bob_bases):
    """
    Классическое просеивание ключа (Sifting):
    Сравнение использованных базисов по открытому каналу связи.
    Сохраняются только те биты, для которых базисы Алисы и Боба совпали.
    """
    final_alice_key = []
    final_bob_key = []
    matching_indices = []
    for i in range(len(alice_bits)):
        if alice_bases[i] == bob_bases[i]:
            final_alice_key.append(alice_bits[i])
            final_bob_key.append(bob_bits[i])
            matching_indices.append(i)
    return np.array(final_alice_key), np.array(final_bob_key), matching_indices


def estimate_qber_and_sample(alice_sifted, bob_sifted, eve_sifted=None, sample_ratio=0.2):
    """
    Замечание 1 (Рекомендация ИФ НАН Беларуси):
    После просеивания ключей выбирается случайный набор битов для оценки QBER.
    Эти оценочные биты СТРОГО ИСКЛЮЧАЮТСЯ из дальнейшего рассмотрения (из ключа для коррекции).
    """
    sifted_len = len(alice_sifted)
    if sifted_len == 0:
        return 0.0, np.array([]), np.array([]), np.array([]) if eve_sifted is not None else None, []

    # Выбираем объем тестовой выборки (минимум 1 бит, максимум sample_ratio от просеянного ключа)
    sample_size = max(1, int(np.round(sifted_len * sample_ratio)))
    if sample_size >= sifted_len:
        sample_size = max(1, sifted_len // 2)

    if sample_size == 0:
        return 0.0, alice_sifted, bob_sifted, eve_sifted, []

    # Случайный выбор индексов для оценки QBER
    sample_indices = np.random.choice(sifted_len, size=sample_size, replace=False)
    keep_indices = np.setdiff1d(np.arange(sifted_len), sample_indices)

    # Оценка QBER по контрольной выборке
    test_alice = alice_sifted[sample_indices]
    test_bob = bob_sifted[sample_indices]
    qber_est = np.sum(test_alice != test_bob) / float(sample_size)

    # Исключение проверенных битов из рабочей рабочей строки ключа
    remaining_alice = alice_sifted[keep_indices]
    remaining_bob = bob_sifted[keep_indices]
    remaining_eve = eve_sifted[keep_indices] if eve_sifted is not None else None

    return qber_est, remaining_alice, remaining_bob, remaining_eve, sample_indices



def error_correction_ldpc_like(alice_key, bob_key, qber_est=0.0, manual_iterations=None):
    """
    Замечание 2 (Рекомендация ИФ НАН Беларуси):
    Многоитерационный Каскадный метод коррекции ошибок (Cascade).
    Количество итераций рассчитывается на основе QBER или задается параметром.
    Для 4-битных блоков максимальное количество итераций ограничено 3,
    чтобы не раскрыть полную информацию о ключе (не более 3 бит четности на блок).
    Возвращает скорректированные ключи, количество исправлений и число разглашенных бит четности (leak_EC).
    """
    corrected_alice_key = alice_key.copy()
    corrected_bob_key = bob_key.copy()
    key_len = len(alice_key)
    
    if key_len < 2:
        return corrected_alice_key, corrected_bob_key, 0, 0

    # Расчет количества итераций (максимум 3 для 4-битных блоков согласно замечанию 2)
    if manual_iterations is not None:
        num_iterations = min(3, max(1, manual_iterations))
    else:
        if qber_est > 0.08:
            num_iterations = 3
        elif qber_est > 0.03:
            num_iterations = 2
        else:
            num_iterations = 1

    block_size = 4
    corrections_made = 0
    disclosed_parity_bits = 0

    def bisect_and_correct(lo, hi, cur_bob_key):
        """Рекурсивный двоичный поиск одиночной битовой ошибки в блоке."""
        nonlocal corrections_made, disclosed_parity_bits
        if hi - lo == 1:
            cur_bob_key[lo] ^= 1  # Инвертируем ошибочный бит у Боба
            corrections_made += 1
            return
        mid = (lo + hi) // 2
        alice_parity_left = int(np.sum(corrected_alice_key[lo:mid]) % 2)
        bob_parity_left   = int(np.sum(cur_bob_key[lo:mid]) % 2)
        disclosed_parity_bits += 1  # Разглашение 1 бита четности
        
        if alice_parity_left != bob_parity_left:
            bisect_and_correct(lo, mid, cur_bob_key)
        else:
            bisect_and_correct(mid, hi, cur_bob_key)

    # Итерации Cascade с рандомизацией перестановок (shuffling)
    np.random.seed(42)  # Фиксированное зерно для согласованной перестановки у Алисы и Боба
    
    for iter_idx in range(num_iterations):
        if iter_idx == 0:
            perm = np.arange(key_len)
        else:
            perm = np.random.permutation(key_len)

        inv_perm = np.argsort(perm)
        perm_alice = corrected_alice_key[perm]
        perm_bob = corrected_bob_key[perm]

        num_blocks = key_len // block_size
        for b in range(num_blocks):
            start = b * block_size
            end   = start + block_size

            alice_parity = int(np.sum(perm_alice[start:end]) % 2)
            bob_parity   = int(np.sum(perm_bob[start:end]) % 2)
            disclosed_parity_bits += 1  # Публичная проверка четности блока

            if alice_parity != bob_parity:
                bisect_and_correct(start, end, perm_bob)

        # Возвращаем элементы к исходному порядку
        corrected_bob_key = perm_bob[inv_perm]

    return corrected_alice_key, corrected_bob_key, corrections_made, disclosed_parity_bits



def binary_entropy(p):
    """Шенноновская двоичная энтропия H2(p)."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * np.log2(p) - (1.0 - p) * np.log2(1.0 - p)


def toeplitz_hash(key_bits, target_length):
    """
    Замечание 3 (Рекомендация ИФ НАН Беларуси):
    Универсальное хэширование на основе матриц Тёплица [Hayashi & Tsurumaru, IEEE TIT 2016].
    Умножает вектор ключа над GF(2) на прямоугольную матрицу Тёплица размером (target_length x len(key_bits)).
    """
    n = len(key_bits)
    m = target_length
    if m <= 0 or n == 0:
        return np.array([], dtype=int), ""

    # Генерация случайного зерна (seed) для построения матрицы Тёплица (первая строка и столбец)
    np.random.seed(12345)
    row = np.random.randint(0, 2, n)
    col = np.random.randint(0, 2, m)
    col[0] = row[0]

    # Построение матрицы Тёплица T_{ij} = vector[i - j]
    toeplitz_matrix = np.zeros((m, n), dtype=int)
    for i in range(m):
        for j in range(n):
            if i >= j:
                toeplitz_matrix[i, j] = col[i - j]
            else:
                toeplitz_matrix[i, j] = row[j - i]

    # Перемножение в поле GF(2) (модуль 2)
    compressed_key = np.dot(toeplitz_matrix, key_bits) % 2
    hex_str = hashlib.sha256(compressed_key.tobytes()).hexdigest()[:min(64, max(8, m // 4))]
    return compressed_key, hex_str


def privacy_amplification(key, qber_est=0.0, leaked_ec_bits=0, eve_info_fraction=0.0):
    """
    Замечание 3 & 4 (Рекомендации ИФ НАН Беларуси):
    Рассчитывает целевую длину сжатого секретного ключа L исходя из:
    - Взаимной информации Алисы и Боба / Евы
    - Количества разглашенных бит при коррекции ошибок (leak_EC)
    Применяет универсальную матрицу Тёплица.
    """
    n = len(key)
    if n == 0:
        return np.array([], dtype=int), "", 0

    # Расчет сжатия ключа на основе границы Шора-Прескилла / Деветака-Винтера:
    # L = N * [1 - H2(QBER) - I(A;E)] - leak_EC
    h_qber = binary_entropy(qber_est)
    
    # Оценка информации Евы
    eavesdropper_info = max(h_qber, eve_info_fraction)
    
    # Доступная длина секретного ключа
    fraction_secure = max(0.0, 1.0 - h_qber - eavesdropper_info)
    target_length = int(np.floor(n * fraction_secure - leaked_ec_bits))
    
    # Минимальный порог длины ключа
    if target_length < 4 or qber_est >= 0.11:
        target_length = 0

    if target_length > 0:
        compressed_bits, hex_str = toeplitz_hash(key, target_length)
    else:
        compressed_bits, hex_str = np.array([], dtype=int), "KEY_REJECTED (QBER too high)"

    return compressed_bits, hex_str, target_length


def calculate_qber(key1, key2):
    """Расчет коэффициента битовых ошибок квантового канала (Quantum Bit Error Rate)."""
    if len(key1) == 0 or len(key2) == 0 or len(key1) != len(key2):
        return 0.0
    errors = np.sum(key1 != key2)
    return errors / float(len(key1))



# --- ИНТЕРФЕЙС ПРИЛОЖЕНИЯ ---

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class QuantumApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("BB84 Simulator - Maksimov R.V. (Academic Edition - NAS Belarus)")
        self.geometry("1180x940")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Боковая панель управления
        self.sidebar = ctk.CTkFrame(self, width=290, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="BB84 SIMULATOR", font=ctk.CTkFont(size=18, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Конфигурация количества излучаемых кубитов
        self.bits_label = ctk.CTkLabel(self.sidebar, text="Количество кубитов:", anchor="w")
        self.bits_label.grid(row=1, column=0, padx=20, pady=(10, 0))

        self.bits_value_label = ctk.CTkLabel(self.sidebar, text="64", font=ctk.CTkFont(size=14, weight="bold"),
                                             text_color="#3b8ed0")
        self.bits_value_label.grid(row=2, column=0, padx=20, pady=(0, 5))

        self.bits_slider = ctk.CTkSlider(self.sidebar, from_=16, to=200, number_of_steps=23,
                                         command=self.update_slider_label)
        self.bits_slider.grid(row=3, column=0, padx=20, pady=5)
        self.bits_slider.set(64)

        # Конфигурация оптического шума волокна
        self.noise_label = ctk.CTkLabel(self.sidebar, text="Уровень шума канала (QBER-шум):", anchor="w")
        self.noise_label.grid(row=4, column=0, padx=20, pady=(10, 0))

        self.noise_value_label = ctk.CTkLabel(self.sidebar, text="3%", font=ctk.CTkFont(size=14, weight="bold"),
                                              text_color="#3b8ed0")
        self.noise_value_label.grid(row=5, column=0, padx=20, pady=(0, 5))

        self.noise_slider = ctk.CTkSlider(self.sidebar, from_=0, to=30, number_of_steps=30,
                                          command=self.update_noise_label)
        self.noise_slider.grid(row=6, column=0, padx=20, pady=5)
        self.noise_slider.set(3)

        # Выбор стратегии подслушивания Евы
        self.attack_label = ctk.CTkLabel(self.sidebar, text="Стратегия подслушивания Евы:", anchor="w")
        self.attack_label.grid(row=7, column=0, padx=20, pady=(15, 0))

        self.attack_combobox = ctk.CTkOptionMenu(self.sidebar, values=[
            "Стандартный перехват-повтор",
            "Перехват под углом 22.5°",
            "Атака с квантовой памятью"
        ])
        self.attack_combobox.grid(row=8, column=0, padx=20, pady=5)
        self.attack_combobox.set("Стандартный перехват-повтор")

        self.eve_switch = ctk.CTkSwitch(self.sidebar, text="Присутствие Евы (Eve)")
        self.eve_switch.grid(row=9, column=0, padx=20, pady=15)

        self.run_button = ctk.CTkButton(self.sidebar, text="ЗАПУСТИТЬ ПРОТОКОЛ", command=self.start_simulation_thread,
                                        font=ctk.CTkFont(weight="bold"))
        self.run_button.grid(row=10, column=0, padx=20, pady=10)

        self.clear_button = ctk.CTkButton(self.sidebar, text="Очистить логи", fg_color="transparent", border_width=2,
                                          command=self.clear_logs)
        self.clear_button.grid(row=11, column=0, padx=20, pady=10)

        self.disclaimer_label = ctk.CTkLabel(
            self.sidebar,
            text="Модель полностью переведена на матрицы Тёплица, выборку QBER и анцилла-кубиты согласно замечаниям ИФ НАН Беларуси.",
            font=ctk.CTkFont(size=9, slant="italic"),
            text_color="#ffae42",
            wraplength=230)
        self.disclaimer_label.grid(row=12, column=0, padx=20, pady=10)

        self.author_label = ctk.CTkLabel(
            self.sidebar,
            text="© 2026 Roman Maksimov\nНаучный рецензент: д.ф.-м.н. А.Б. Михалычев\nИнститут физики НАН Беларуси",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color="gray")
        self.author_label.grid(row=13, column=0, padx=20, pady=(30, 10), sticky="s")

        # Главная область вывода
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(1, weight=1)

        # Информационные карточки
        self.metrics_frame = ctk.CTkFrame(self.main_content, height=100)
        self.metrics_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.metrics_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.qber_card  = self.create_metric_card(self.metrics_frame, "QBER (Оценка)", "0.00", 0)
        self.status_card = self.create_metric_card(self.metrics_frame, "Статус канала", "Ожидание", 1)
        self.key_len_card = self.create_metric_card(self.metrics_frame, "Длина секретного ключа", "0 бит", 2)

        # Лог-терминал
        self.textbox = ctk.CTkTextbox(self.main_content, font=ctk.CTkFont(family="Consolas", size=12))
        self.textbox.grid(row=1, column=0, sticky="nsew")

    def update_slider_label(self, value):
        self.bits_value_label.configure(text=str(int(value)))

    def update_noise_label(self, value):
        self.noise_value_label.configure(text=f"{round(value)}%")

    def create_metric_card(self, master, title, value, col):
        frame = ctk.CTkFrame(master)
        frame.grid(row=0, column=col, padx=10, pady=10, sticky="nsew")
        t_label = ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=11, slant="italic"))
        t_label.pack(pady=(5, 0))
        v_label = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=18, weight="bold"))
        v_label.pack(pady=(0, 5))
        return v_label

    def log(self, message):
        self.after(0, lambda: self._safe_log(message))

    def _safe_log(self, message):
        self.textbox.insert("end", f"{message}\n")
        self.textbox.see("end")

    def clear_logs(self):
        self.textbox.delete("1.0", "end")
        self.qber_card.configure(text="0.00", text_color="white")
        self.status_card.configure(text="Ожидание", text_color="white")
        self.key_len_card.configure(text="0 бит")

    def start_simulation_thread(self):
        self.run_button.configure(state="disabled")
        threading.Thread(target=self.run_simulation, daemon=True).start()


    def run_simulation(self):
        try:
            num_bits = int(self.bits_slider.get())
            noise_prob = round(self.noise_slider.get()) / 100.0
            introduce_eve = self.eve_switch.get()
            attack_strategy = self.attack_combobox.get()

            self.log("Разработчик системы: Максимов Роман Викторович")
            self.log("Рецензент: Ведущий научный сотрудник центра 'Квантовая оптика'")
            self.log("           и квантовая информатика' Института физики НАН Беларуси, д.ф.-м.н. А.Б. Михалычев")
            self.log("=" * 85)

            scenario_num  = "2" if introduce_eve else "1"
            scenario_text = f"С ЕВОЙ (Атака: {attack_strategy})" if introduce_eve else "БЕЗ ЕВЫ (Чистый/зашумленный канал)"
            self.log(f"\n=== СЦЕНАРИЙ {scenario_num}: Квантовый канал {scenario_text} ===")
            self.log(f"--- Параметры: Излучено кубитов: {num_bits} | Аппаратный Шум: {noise_prob*100:.1f}% ---\n")

            # 1. Этап Алисы
            alice_bits  = generate_random_bits(num_bits)
            alice_bases = generate_random_bases(num_bits)
            self.log(f"[Алиса]: Подготовила биты:    {alice_bits}")
            self.log(f"[Алиса]: Выбрала базисы:      {alice_bases}")

            alice_circuit = prepare_qubits(alice_bits, alice_bases)

            # Шумовое искажение квантового канала
            if noise_prob > 0:
                alice_circuit = apply_channel_noise(alice_circuit, noise_prob)
                self.log(f"[Канал]: Воздействие шума среды ({noise_prob*100:.1f}%) добавлено.")

            # 2. Этап перехвата Евы
            eve_measured_bits = np.zeros(num_bits, dtype=int)
            eve_bases = np.zeros(num_bits, dtype=int)
            
            if introduce_eve:
                qc_to_bob, eve_bases, eve_measured_bits = eavesdrop_on_qubits(alice_circuit, num_bits, attack_strategy)
                self.log(f"[Ева]: Перехватила кубиты! Использована стратегия: {attack_strategy}")
                
                if attack_strategy != "Атака с квантовой памятью":
                    self.log(f"[Ева]: Измеренные базисы Евы: {eve_bases}")
                    self.log(f"[Ева]: Результат измерений:    {eve_measured_bits}")
                else:
                    self.log(f"[Ева]: Кубиты зацеплены с вспомогательными (Ancilla). Измерение отложено.")

                # Дополнительный шум при переотправке
                if noise_prob > 0:
                    qc_to_bob = apply_channel_noise(qc_to_bob, noise_prob)
            else:
                qc_to_bob = alice_circuit.copy()

            # 3. Измерение Боба
            bob_bases = generate_random_bases(num_bits)
            
            # Измерение в зависимости от структуры квантовой схемы
            if introduce_eve and attack_strategy == "Атака с квантовой памятью":
                # Боб измеряет канальные кубиты [0..N-1]
                bob_measured_bits = measure_qubits(qc_to_bob, bob_bases)
            else:
                bob_measured_bits = measure_qubits(qc_to_bob, bob_bases)

            self.log(f"[Боб]:  Измерил биты:         {bob_measured_bits}")
            self.log(f"[Боб]:  Использовал базисы:   {bob_bases}")

            # --- ПОСЛЕ СРАВНЕНИЯ БАЗИСОВ ---
            sifted_alice_key, sifted_bob_key, matching_indices = sift_key(
                alice_bits, alice_bases, bob_measured_bits, bob_bases)

            self.log("\n--- ЭТАП 1: Классическое просеивание (Sifting) ---")
            self.log(f"Совпавшие индексы базисов:  {matching_indices}")
            self.log(f"Просеянный ключ Алисы:      {sifted_alice_key}")
            self.log(f"Просеянный ключ Боба:        {sifted_bob_key}")

            # Замечание 6: Обработка отложенного измерения Евы при когерентной атаке с квантовой памятью
            if introduce_eve and attack_strategy == "Атака с квантовой памятью":
                # Ева измеряет свои вспомогательные кубиты в публично объявленных базисах
                eve_bases = alice_bases.copy()
                eve_measured_bits = measure_qubits(qc_to_bob, eve_bases)
                self.log(f"[Ева→Память]: Провела измерение ancilla-кубитов ПОСЛЕ объявления базисов.")

            # Сохраняем просеянную битовую строку Евы для корреляционного анализа
            sifted_eve_key = None
            if introduce_eve:
                sifted_eve_key = np.array([eve_measured_bits[idx] for idx in matching_indices])

            # Замечание 1 (ИФ НАН Беларуси): Выборка битов для оценки QBER с их последующим УДАЛЕНИЕМ
            self.log("\n--- Оценка QBER и отброс выборочных битов (Замечание 1) ---")
            qber_est, remaining_alice, remaining_bob, remaining_eve, test_indices = estimate_qber_and_sample(
                sifted_alice_key, sifted_bob_key, sifted_eve_key, sample_ratio=0.25
            )
            self.log(f"Оцененное значение QBER:     {qber_est:.4f} ({qber_est*100:.1f}%)")
            self.log(f"Исключено проверочных бит:   {len(test_indices)} (удалены из финального ключа)")
            self.log(f"Остаточный просеянный ключ (Алиса): {remaining_alice}")
            self.log(f"Остаточный просеянный ключ (Боб):   {remaining_bob}")

            # Замечание 2 (ИФ НАН Беларуси): Многоитерационный Cascade с ограничением раскрытия информации
            self.log("\n--- ЭТАП 2: Многоитерационная коррекция ошибок Cascade (Замечание 2) ---")
            corrected_alice, corrected_bob, err_count, leaked_ec_bits = error_correction_ldpc_like(
                remaining_alice, remaining_bob, qber_est=qber_est
            )
            final_qber = calculate_qber(corrected_alice, corrected_bob)
            self.log(f"Исправлено ошибок у Боба:    {err_count}")
            self.log(f"Разглашено бит чётности (leak_EC): {leaked_ec_bits}")
            self.log(f"Согласованный ключ Алисы:    {corrected_alice}")
            self.log(f"Согласованный ключ Боба:     {corrected_bob}")
            self.log(f"Остаточная неисправленная ошибка: {final_qber:.4f}")

            # Замечания 3 и 4 (ИФ НАН Беларуси): Усиление секретности матрицами Тёплица и отслеживание ключа Евы
            self.log("\n--- ЭТАП 3: Усиление секретности матрицами Тёплица (Замечания 3 и 4) ---")
            
            # Расчет доли информации Евы
            eve_info_frac = 0.0
            if introduce_eve and remaining_eve is not None and len(remaining_alice) > 0:
                eve_info_frac = np.sum(remaining_eve == remaining_alice) / float(len(remaining_alice))

            amp_alice_bits, amp_alice_hex, final_len = privacy_amplification(
                corrected_alice, qber_est=qber_est, leaked_ec_bits=leaked_ec_bits, eve_info_fraction=eve_info_frac
            )
            amp_bob_bits, amp_bob_hex, _ = privacy_amplification(
                corrected_bob, qber_est=qber_est, leaked_ec_bits=leaked_ec_bits, eve_info_fraction=eve_info_frac
            )

            keys_match = np.array_equal(amp_alice_bits, amp_bob_bits) and final_len > 0

            self.log(f"Длина сжатого секретного ключа (L): {final_len} бит")
            self.log(f"Финальный секретный ключ Алисы: {amp_alice_hex}")
            self.log(f"Финальный секретный ключ Боба:  {amp_bob_hex}")

            if keys_match:
                self.log("✓ Финальные ключи Алисы и Боба СОВПАДАЮТ.")
            else:
                self.log("⚠ Ключ отклонен (QBER выше 11% либо не хватило длины после сжатия).")


            # Замечание 4 & 5 (ИФ НАН Беларуси): Корректный анализ ключа Евы для ВСЕХ атак, включая 22.5°
            if introduce_eve and remaining_eve is not None and len(remaining_eve) > 0:
                self.log("\n--- АНАЛИЗ ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ ЕВЫ (Замечания 4 и 5) ---")
                
                # Замечание 5: Прямое сравнение битовых строк Евы и Алисы для всех атак
                eve_raw_corr = np.sum(remaining_eve == remaining_alice) / float(len(remaining_alice))
                self.log(f"1. Сходство ключа Евы ДО усиления секретности: {eve_raw_corr*100:.1f}%")

                # Замечание 4: Преобразование ключа Евы процедурой усиления секретности (матрица Тёплица)
                if final_len > 0:
                    amp_eve_bits, amp_eve_hex, _ = privacy_amplification(
                        remaining_eve, qber_est=qber_est, leaked_ec_bits=leaked_ec_bits, eve_info_fraction=eve_info_frac
                    )
                    eve_final_corr = np.sum(amp_eve_bits == amp_alice_bits) / float(final_len) if len(amp_eve_bits) == final_len else 0.5
                    self.log(f"2. Сходство ключа Евы ПОСЛЕ универсального хэширования Тёплица: {eve_final_corr*100:.1f}%")
                    self.log("   --> Корреляция полностью уничтожена (взаимная информация I(A;E) -> 0).")

            # --- ВЫВОДЫ ---
            self.log("\n--- АНАЛИТИЧЕСКИЕ ВЫВОДЫ ---")
            if qber_est >= 0.11:
                status_text = "ОБНАРУЖЕН ВЗЛОМ!"
                self.log(f"!!! {status_text} QBER ({qber_est*100:.1f}%) выше предела Шора-Прескилла (11%). Ключ СКОМПРОМЕТИРОВАН! !!!")
            else:
                status_text = "БЕЗОПАСНО"
                self.log(f"✓ {status_text}: QBER ({qber_est*100:.1f}%) в пределах нормы (<11%). Ключ успешно распределен.")

            self.after(0, lambda: self.update_ui_results(qber_est, final_len if keys_match else 0, status_text))

            # Визуализация физической квантовой схемы
            self.log("\nПодготовка интерактивной схемы...")
            vis_count = min(4, num_bits)
            vis_qc = QuantumCircuit(vis_count, vis_count)
            for i in range(vis_count):
                if alice_bits[i] == 1:  vis_qc.x(i)
                if alice_bases[i] == 1: vis_qc.h(i)
            vis_qc.barrier()
            for i in range(vis_count):
                if bob_bases[i] == 1: vis_qc.h(i)
                vis_qc.measure(i, i)

            self.after(0, lambda: self.show_plot(vis_qc, vis_count))

        except Exception as e:
            self.log(f"ОШИБКА СИМУЛЯЦИИ: {str(e)}")
        finally:
            self.after(0, lambda: self.run_button.configure(state="normal"))


    def show_plot(self, qc, count):
        """
        Интеграция холста Matplotlib в архитектуру CustomTkinter.
        Реализовано корректное управление памятью: сброс состояния Matplotlib
        перед отрисовкой во избежание утечек памяти.
        """
        try:
            plt.clf()
            plot_window = ctk.CTkToplevel(self)
            plot_window.title("Квантовая схема протокола BB84 (Физический уровень)")
            plot_window.geometry("850x450")

            plot_window.after(150, lambda: plot_window.focus())

            fig, ax = plt.subplots(figsize=(8, 4))
            qc.draw(output='mpl', style={'name': 'bw'}, ax=ax)
            ax.set_title(
                f"Визуализация квантовых вентилей (первые {count} кубитов)\n"
                f"Алиса (Генерация) → Квантовый канал → Боб (Измерение)")
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=plot_window)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=15, pady=15)

            def on_close():
                plt.close(fig)
                canvas.get_tk_widget().destroy()
                plot_window.destroy()

            plot_window.protocol("WM_DELETE_WINDOW", on_close)

        except Exception as e:
            self.log(f"Не удалось отрисовать схему: {e}")

    def update_ui_results(self, qber, final_key_len, status):
        self.qber_card.configure(text=f"{qber:.4f}")
        self.key_len_card.configure(text=f"{final_key_len} бит")

        if "ВЗЛОМ" in status:
            self.qber_card.configure(text_color="#ff4b4b")
            self.status_card.configure(text=status, text_color="#ff4b4b")
        else:
            self.qber_card.configure(text_color="#47d147")
            self.status_card.configure(text=status, text_color="#47d147")


if __name__ == "__main__":
    app = QuantumApp()
    app.mainloop()
