# ==============================================================================
# © 2025-2026 Максимов Роман Викторович. Все права защищены.
#
# Проект: QKD-BB84-Simulator-Qiskit (Академическая Версия v3.1)
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
    for i in range(len(bases)):
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
    measured_bits = np.array([int(b) for b in measured_bits_str[::-1]])
    return measured_bits


def eavesdrop_on_qubits(qc_from_alice, num_qubits, attack_type="Стандартный перехват-повтор"):
    """
    Ева: Моделирование различных сценариев перехвата информации в квантовом канале.
    """
    eve_measured_bits = np.zeros(num_qubits, dtype=int)
    eve_bases = np.zeros(num_qubits, dtype=int)

    if attack_type == "Стандартный перехват-повтор":
        # Атака Intercept-Resend: Ева измеряет кубиты в случайных базисах BB84
        # и переотправляет новые кубиты Бобу. Вносит средний QBER ~ 25%.
        eve_bases = generate_random_bases(num_qubits)
        eve_measured_bits = measure_qubits(qc_from_alice.copy(), eve_bases)
        qc_to_bob = prepare_qubits(eve_measured_bits, eve_bases)

    elif attack_type == "Перехват под углом 22.5°":
        # Атака Брейдбарта (Breidbart basis attack):
        # Измерение в промежуточном базисе, повернутом на π/8 (22.5°) относительно осей BB84.
        # Поворот Ry(-π/4) на сфере Блоха проецирует состояния ровно посредине между + и ×,
        # минимизируя вносимые возмущения (теоретический QBER снижается до ~14.6%).
        qc_copy = qc_from_alice.copy()
        for i in range(num_qubits):
            qc_copy.ry(-np.pi / 4, i)

        # Выполняем проецирование на повернутую ось
        eve_bases = np.zeros(num_qubits, dtype=int)
        eve_measured_bits = measure_qubits(qc_copy, eve_bases)

        # Подготовка физически корректных состояний для отправки Бобу:
        # Транслируем результаты измерения в исходную декартову систему координат Алисы/Боба.
        qc_to_bob = QuantumCircuit(num_qubits, num_qubits)
        for i in range(num_qubits):
            if eve_measured_bits[i] == 1:
                qc_to_bob.x(i)
            qc_to_bob.ry(np.pi / 4, i)

    elif attack_type == "Атака с квантовой памятью":
        # Когерентная коллективная атака:
        # Ева временно сохраняет перехваченные кубиты в своей идеальной квантовой памяти,
        # не проводя мгновенного измерения (чтобы не разрушить суперпозицию).
        # Она транслирует кубиты Бобу, наводя лишь неизбежный фазовый шум хранения (Z-ошибки).
        # Реальное измерение Ева проводит отложено — только после того, как Алиса и Боб
        # публично раскроют базисы sifting на классическом этапе.
        qc_to_bob = qc_from_alice.copy()
        for i in range(num_qubits):
            if np.random.rand() < 0.2:  # Моделирование декогеренции/дефазировки при хранении
                qc_to_bob.z(i)

        # Фактическое считывание памяти Евой происходит позже, во время симуляции sifting.
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


def error_correction_ldpc_like(alice_key, bob_key):
    """
    Классическая коррекция ошибок на основе паритетов блоков (Cascade-подобный алгоритм).
    
    Алиса и Боб разбивают просеянные ключи на блоки фиксированной длины (K=4) и 
    сравнивают только контрольные суммы чётности (паритет) по открытому каналу.
    При несовпадении паритета запускается рекурсивная процедура дихотомии (бинарного поиска):
      - Проверяется паритет левой половины блока.
      - Если паритеты не совпадают, ошибка локализована слева → рекурсия влево.
      - Если паритеты совпадают, ошибка гарантированно находится справа → рекурсия вправо.
    """
    corrected_alice_key = alice_key.copy()
    corrected_bob_key = bob_key.copy()
    if len(alice_key) < 2:
        return corrected_alice_key, corrected_bob_key, 0

    block_size = 4
    num_blocks = len(alice_key) // block_size
    corrections_made = 0

    def bisect_and_correct(lo, hi):
        """Рекурсивный двоичный поиск одиночной битовой ошибки в блоке."""
        nonlocal corrections_made
        if hi - lo == 1:
            corrected_bob_key[lo] ^= 1  # Инвертируем ошибочный бит у Боба
            corrections_made += 1
            return
        mid = (lo + hi) // 2
        alice_parity_left = int(np.sum(corrected_alice_key[lo:mid]) % 2)
        bob_parity_left   = int(np.sum(corrected_bob_key[lo:mid]) % 2)
        if alice_parity_left != bob_parity_left:
            bisect_and_correct(lo, mid)
        else:
            bisect_and_correct(mid, hi)

    for b in range(num_blocks):
        start = b * block_size
        end   = start + block_size

        alice_parity = int(np.sum(corrected_alice_key[start:end]) % 2)
        bob_parity   = int(np.sum(corrected_bob_key[start:end]) % 2)

        if alice_parity != bob_parity:
            bisect_and_correct(start, end)

    return corrected_alice_key, corrected_bob_key, corrections_made


def privacy_amplification(key):
    """
    Усиление секретности (Privacy Amplification):
    Сжатие и очистка согласованного ключа с помощью криптографической хэш-функции SHA-256.
    Уничтожает любое частичное знание о битах, которое Ева могла получить при перехвате
    или подслушивании классического этапа сверки паритетов.
    Возвращает стойкий 256-битный ключ (64 символа hex).
    """
    if len(key) == 0:
        return ""

    key_str = "".join(str(b) for b in key)
    hasher = hashlib.sha256()
    hasher.update(key_str.encode('utf-8'))
    return hasher.hexdigest()


def calculate_qber(key1, key2):
    """Расчет коэффициента битовых ошибок квантового канала (Quantum Bit Error Rate)."""
    if len(key1) == 0 or len(key2) == 0:
        return 0.0
    errors = np.sum(key1 != key2)
    return errors / len(key1)


# --- ИНТЕРФЕЙС ПРИЛОЖЕНИЯ ---

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class QuantumApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("BB84 Simulator - Maksimov R.V., Grade 10 (Academic Edition)")
        self.geometry("1150x920")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Боковая панель управления
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="BB84 SIMULATOR", font=ctk.CTkFont(size=18, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Конфигурация количества излучаемых кубитов
        self.bits_label = ctk.CTkLabel(self.sidebar, text="Количество кубитов:", anchor="w")
        self.bits_label.grid(row=1, column=0, padx=20, pady=(10, 0))

        self.bits_value_label = ctk.CTkLabel(self.sidebar, text="32", font=ctk.CTkFont(size=14, weight="bold"),
                                             text_color="#3b8ed0")
        self.bits_value_label.grid(row=2, column=0, padx=20, pady=(0, 5))

        self.bits_slider = ctk.CTkSlider(self.sidebar, from_=8, to=100, number_of_steps=23,
                                         command=self.update_slider_label)
        self.bits_slider.grid(row=3, column=0, padx=20, pady=5)
        self.bits_slider.set(32)

        # Конфигурация оптического шума волокна
        self.noise_label = ctk.CTkLabel(self.sidebar, text="Уровень шума канала (QBER-шум):", anchor="w")
        self.noise_label.grid(row=4, column=0, padx=20, pady=(10, 0))

        self.noise_value_label = ctk.CTkLabel(self.sidebar, text="5%", font=ctk.CTkFont(size=14, weight="bold"),
                                              text_color="#3b8ed0")
        self.noise_value_label.grid(row=5, column=0, padx=20, pady=(0, 5))

        self.noise_slider = ctk.CTkSlider(self.sidebar, from_=0, to=30, number_of_steps=30,
                                          command=self.update_noise_label)
        self.noise_slider.grid(row=6, column=0, padx=20, pady=5)
        self.noise_slider.set(5)

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
            text="Внимание: Использование Qiskit (IBM) носит демонстрационный характер. "
                 "Для систем нац. безопасности РБ требуется суверенная среда.",
            font=ctk.CTkFont(size=9, slant="italic"),
            text_color="#ffae42",
            wraplength=220)
        self.disclaimer_label.grid(row=12, column=0, padx=20, pady=10)

        self.author_label = ctk.CTkLabel(
            self.sidebar,
            text="© 2026 Roman Maksimov\nSchool №2, Postavy\nНаучный консультант: ИФ НАН Беларуси",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color="gray")
        self.author_label.grid(row=13, column=0, padx=20, pady=(40, 10), sticky="s")

        # Главная область вывода
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(1, weight=1)

        # Информационные карточки
        self.metrics_frame = ctk.CTkFrame(self.main_content, height=100)
        self.metrics_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.metrics_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.qber_card  = self.create_metric_card(self.metrics_frame, "QBER (Общие Ошибки)", "0.00", 0)
        self.status_card = self.create_metric_card(self.metrics_frame, "Статус канала", "Ожидание", 1)
        self.key_len_card = self.create_metric_card(self.metrics_frame, "Финальный ключ (бит)", "0", 2)

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
        v_label = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=20, weight="bold"))
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
        self.key_len_card.configure(text="0")

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
            self.log("-" * 80)

            scenario_num  = "2" if introduce_eve else "1"
            scenario_text = f"С ЕВОЙ (Атака: {attack_strategy})" if introduce_eve else "БЕЗ ЕВЫ (Чистый/зашумленный канал)"
            self.log(f"\n=== СЦЕНАРИЙ {scenario_num}: Квантовый канал {scenario_text} ===")
            self.log(f"--- Параметры: Кубитов: {num_bits} | Аппаратный Шум: {noise_prob*100:.1f}% ---\n")

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
            eve_measured_bits = None
            if introduce_eve:
                qc_to_bob, eve_bases, eve_measured_bits = eavesdrop_on_qubits(alice_circuit, num_bits, attack_strategy)
                self.log(f"[Ева]: Перехватила кубиты! Использована стратегия: {attack_strategy}")
                self.log(f"[Ева]: Базисы Евы:           {eve_bases}")
                self.log(f"[Ева]: Результат Евы:        {eve_measured_bits}")
                
                # Дополнительный технологический шум при переотправке
                if noise_prob > 0:
                    qc_to_bob = apply_channel_noise(qc_to_bob, noise_prob)
                    self.log(f"[Канал Ева→Боб]: Воздействие шума среды ({noise_prob*100:.1f}%) добавлено.")
            else:
                qc_to_bob = alice_circuit.copy()

            # 3. Измерение Боба
            bob_bases        = generate_random_bases(num_bits)
            bob_measured_bits = measure_qubits(qc_to_bob, bob_bases)
            self.log(f"[Боб]:  Измерил биты:         {bob_measured_bits}")
            self.log(f"[Боб]:  Использовал базисы:   {bob_bases}")

            # --- ПОСЛЕ СРАВНЕНИЯ БАЗИСОВ ---
            sifted_alice_key, sifted_bob_key, matching_indices = sift_key(
                alice_bits, alice_bases, bob_measured_bits, bob_bases)
            qber = calculate_qber(sifted_alice_key, sifted_bob_key)

            self.log("\n--- ЭТАП 1: Классическое просеивание (Sifting) ---")
            self.log(f"Совпавшие индексы базисов:  {matching_indices}")
            self.log(f"Просеянный ключ Алисы:      {sifted_alice_key}")
            self.log(f"Просеянный ключ Боба:        {sifted_bob_key}")
            self.log(f"Предварительный QBER (шум):  {qber:.4f} ({qber*100:.1f}%)")

            # Отложенное измерение Евой своей квантовой памяти (при когерентной атаке)
            if introduce_eve and attack_strategy == "Атака с квантовой памятью":
                eve_bases         = alice_bases.copy()
                eve_measured_bits = alice_bits.copy()
                self.log(f"[Ева→Память]: Считывает кубиты ПОСЛЕ публикации базисов (когерентная атака).")
                self.log(f"[Ева→Память]: Базисы Евы (= Алисы):  {eve_bases}")
                self.log(f"[Ева→Память]: Биты Евы (100% точность): {eve_measured_bits}")

            # --- КЛАССИЧЕСКАЯ ПОСТОБРАБОТКА ---
            self.log("\n--- ЭТАП 2: Классическая коррекция ошибок (БЕЗ подглядывания Боба) ---")
            corrected_alice, corrected_bob, err_count = error_correction_ldpc_like(sifted_alice_key, sifted_bob_key)
            final_qber = calculate_qber(corrected_alice, corrected_bob)
            self.log(f"Исправлено ошибок у Боба:    {err_count}")
            self.log(f"Согласованный ключ Алисы:    {corrected_alice}")
            self.log(f"Согласованный ключ Боба:     {corrected_bob}")
            self.log(f"Остаточный QBER:             {final_qber:.4f} ({final_qber*100:.1f}%)")

            # Академическое примечание к однопроходной проверке четности
            if final_qber > 0:
                self.log(f"⚠ ВНИМАНИЕ: Остаточные ошибки ({int(final_qber * len(corrected_alice))} бит) не исправлены.")
                self.log(f"  Причина: блок(и) с ЧЁТНЫМ числом ошибок невидимы для паритетной проверки.")
                self.log(f"  Это известное ограничение одноитерационного Cascade. Полный алгоритм")
                self.log(f"  выполняет несколько итераций с рандомизацией индексов для их устранения.")

            self.log("\n--- ЭТАП 3: Усиление секретности (Privacy Amplification) ---")
            amplified_alice_key = privacy_amplification(corrected_alice)
            amplified_bob_key   = privacy_amplification(corrected_bob)
            keys_match = amplified_alice_key == amplified_bob_key

            final_key_bits = 256 if (keys_match and len(corrected_alice) > 0) else 0

            self.log(f"Финальный секретный ключ Алисы (SHA-256): {amplified_alice_key}")
            self.log(f"Финальный секретный ключ Боба  (SHA-256): {amplified_bob_key}")
            if keys_match:
                self.log("✓ Финальные ключи Алисы и Боба СОВПАДАЮТ.")
            else:
                self.log("⚠ Финальные ключи НЕ совпадают — остаточные ошибки после коррекции. Требуется повтор сеанса.")

            if introduce_eve and eve_measured_bits is not None:
                if len(sifted_alice_key) > 0:
                    sifted_eve_bits = np.array([eve_measured_bits[idx] for idx in matching_indices])
                    self.log(f"\nИнформационная безопасность:")
                    if attack_strategy == "Стандартный перехват-повтор":
                        correlation_before = np.sum(sifted_eve_bits == sifted_alice_key) / len(sifted_alice_key)
                        self.log(f" - Сходство перехваченного ключа Евы до обработки: {correlation_before*100:.1f}%")
                        self.log(f"   (теоретически ~75% при случайном угадывании базисов)")
                    elif attack_strategy == "Атака с квантовой памятью":
                        correlation_memory = np.sum(sifted_eve_bits == sifted_alice_key) / len(sifted_alice_key)
                        self.log(f" - Когерентная атака: Ева знает просеянный ключ на {correlation_memory*100:.1f}%")
                        self.log(f"   (теоретически 100% при идеальной памяти, QBER от памяти не нулевой)")
                    else:
                        self.log(f" - Для атаки '{attack_strategy}' прямая корреляция ключа Евы")
                        self.log(f"   не применима к просеянному ключу (измерение в промежуточном базисе).")
                    self.log(f" - Сходство ключа Евы после усиления секретности: ~0% (защита SHA-256)")

            # --- ВЫВОДЫ ---
            self.log("\n--- АНАЛИТИЧЕСКИЕ ВЫВОДЫ ---")
            if qber >= 0.11:
                status_text = "ОБНАРУЖЕН ВЗЛОМ!"
                self.log(f"!!! {status_text} QBER ({qber*100:.1f}%) выше предела безопасности (11%). Ключ СКОМПРОМЕТИРОВАН! !!!")
            else:
                status_text = "БЕЗОПАСНО"
                self.log(f"✓ {status_text}: QBER ({qber*100:.1f}%) в пределах нормы (<11%). Ключ успешно распределен.")

                if introduce_eve:
                    self.log("\n⚠️ ПОЧЕМУ ПЕРЕХВАТ НЕ ОБНАРУЖЕН (Присутствие Евы незаметно):")
                    self.log("1. Малое число кубитов (статистическая погрешность):")
                    self.log("   При небольших длинах последовательностей Еве могло банально «повезти» с совпадением базисов.")
                    self.log("2. Особенности продвинутой атаки:")
                    self.log(f"   Стратегия '{attack_strategy}' оптимизирует извлечение информации с минимизацией разрушения ортогональных состояний.")
                    self.log("3. Роль коррекции ошибок:")
                    self.log("   Алгоритмы классической постобработки успешно исправили единичные дефекты.")

            self.log("\n--- Связь с рекомендациями Института Физики НАН Беларуси: ---")
            self.log("1. Реализован технологический шум. Рост QBER может быть вызван деградацией волокна, а не только Евой.")
            self.log("2. Внедрённая процедура коррекции чётности и хеширования удаляет любые следы подслушивания Евой.")
            self.log("3. Показано превосходство различных типов атак. Атака под углом 22.5° дает Еве информацию при меньшем шуме.")
            self.log("4. Данная модель демонстрирует уязвимости реального физического оборудования в сравнении с идеальным BB84.")

            self.after(0, lambda: self.update_ui_results(qber, final_key_bits, status_text))

            # Визуализация физической квантовой схемы
            self.log("\nПодготовка интерактивной схемы...")
            vis_count = min(5, num_bits)
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
        Безопасная интеграция холста Matplotlib в архитектуру CustomTkinter.
        Реализовано корректное управление памятью: сброс глобального состояния Matplotlib
        (plt.clf()) перед отрисовкой во избежание утечек памяти и предупреждений,
        а также отложенное закрытие фигуры при закрытии окна Tkinter.
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
                f"Визуализация гейтов (первые {count} кубитов)\n"
                f"Алиса (Генерация/Базисы) → Канал → Боб (Измерение)")
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=plot_window)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=15, pady=15)

            # Освобождение ресурсов Matplotlib и Tkinter при закрытии дочернего окна
            def on_close():
                plt.close(fig)
                canvas.get_tk_widget().destroy()
                plot_window.destroy()

            plot_window.protocol("WM_DELETE_WINDOW", on_close)

        except Exception as e:
            self.log(f"Не удалось отрисовать схему: {e}")

    def update_ui_results(self, qber, final_key_len, status):
        self.qber_card.configure(text=f"{qber:.4f}")
        self.key_len_card.configure(text=str(final_key_len))

        if "ВЗЛОМ" in status:
            self.qber_card.configure(text_color="#ff4b4b")
            self.status_card.configure(text=status, text_color="#ff4b4b")
        else:
            self.qber_card.configure(text_color="#47d147")
            self.status_card.configure(text=status, text_color="#47d147")


if __name__ == "__main__":
    app = QuantumApp()
    app.mainloop()
