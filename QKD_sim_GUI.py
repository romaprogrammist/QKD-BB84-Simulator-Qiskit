# ==============================================================================
# © 2025-2026 Максимов Роман Викторович. Все права защищены.
#
# Проект: QKD-BB84-Simulator-Qiskit (Версия v3.3fix)
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


def calculate_fiber_transmission(distance_km, attenuation_db_per_km=0.2):
    """
    Вычисляет коэффициент пропускания оптического волокна (Transmission T):
    T = 10^(-alpha * L / 10)
    где alpha - затухание в дБ/км, L - длина линии связи в км.
    """
    return 10 ** (-(attenuation_db_per_km * distance_km) / 10.0)


def calculate_physical_qber(
    distance_km,
    attenuation_db=0.2,
    det_efficiency=0.25,
    dark_count_rate=1e-6,
    afterpulsing_prob=0.005,
    optics_error=0.015,
    mean_photon_num=0.1,
):
    """
    Расчет физического уровня ошибок QBER(phys) и соотношения сигнал/шум (SNR)
    согласно оптической модели линии связи и квантовым детекторам (SPAD/SNSPD):
    QBER(phys) = P_dark / (2 * (T * eta_det * mu + P_dark)) + Optics_Error
    """
    T = calculate_fiber_transmission(distance_km, attenuation_db)

    # Эффективная вероятность темнового отсчета с учетом послеимпульсов (afterpulsing)
    p_dark_total = dark_count_rate + afterpulsing_prob * dark_count_rate

    # Вероятность регистрации полезного сигнала на импульс
    p_signal = T * det_efficiency * mean_photon_num

    # Полное суммарное знаменательное выражение регистрации
    total_detection_prob = p_signal + p_dark_total

    if total_detection_prob <= 0:
        return 0.5, 0.0, 0.0

    # Расчет физического QBER
    qber_phys = (p_dark_total / (2.0 * total_detection_prob)) + optics_error
    qber_phys = min(0.5, qber_phys)

    # Соотношение сигнал/шум (SNR)
    snr = p_signal / p_dark_total if p_dark_total > 0 else 1e6

    return qber_phys, snr, total_detection_prob


def calculate_secret_key_rate(
    distance_km,
    repetition_rate_hz=1e8,
    attenuation_db=0.2,
    det_efficiency=0.25,
    dark_count_rate=1e-6,
    afterpulsing_prob=0.005,
    optics_error=0.015,
    mean_photon_num=0.1,
    ec_efficiency=1.16,
):
    """
    Расчет скорости генерации секретного ключа (Secret Key Rate - SKR) на основе:
    - Частоты повторения импульсов f
    - Доли полезного ключа (Net Key Fraction r_net)
    - Границы Деветака-Винтера / Шора-Прескилла
    SKR = f * P_click * 0.5 * r_net
    """
    qber_phys, snr, p_click = calculate_physical_qber(
        distance_km,
        attenuation_db,
        det_efficiency,
        dark_count_rate,
        afterpulsing_prob,
        optics_error,
        mean_photon_num,
    )

    if qber_phys >= 0.11:  # Предел безопасности BB84
        return 0.0, qber_phys, snr, 0.0

    # Двоичная энтропия Шеннона
    h2_qber = binary_entropy(qber_phys)

    # Доля полезного ключа после коррекции ошибок (f_EC * H2) и усиления секретности (H2)
    net_key_fraction = max(0.0, 1.0 - (ec_efficiency + 1.0) * h2_qber)

    # Скорость просеянного ключа (Sifted Key Rate) при p_sift = 0.5
    sifted_rate = repetition_rate_hz * p_click * 0.5

    # Секретная скорость генерации ключа (бит/сек)
    skr = sifted_rate * net_key_fraction
    return skr, qber_phys, snr, net_key_fraction


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
    """
    if noise_probability <= 0:
        return qc

    for i in range(qc.num_qubits):
        if np.random.rand() < noise_probability:
            error_type = np.random.randint(0, 3)
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
    Для измерения в диагональном базисе предварительно применяется гейт Адамара (H).
    """
    qc_copy = qc_to_measure.copy()
    num_m_qubits = len(bases)
    for i in range(num_m_qubits):
        if bases[i] == 1:
            qc_copy.h(i)
        qc_copy.measure(i, i)

    try:
        simulator = AerSimulator(method="matrix_product_state")
        job = simulator.run(qc_copy, shots=1)
        result = job.result().get_counts()
    except Exception:
        simulator = AerSimulator()
        job = simulator.run(qc_copy, shots=1)
        result = job.result().get_counts()

    measured_bits_str = list(result.keys())[0]
    measured_bits = np.array([int(b) for b in measured_bits_str[::-1][:num_m_qubits]])
    return measured_bits


def eavesdrop_on_qubits(qc_from_alice, num_qubits, attack_type="Стандартный перехват-повтор"):
    """
    Ева: Моделирование различных сценариев перехвата информации в квантовом канале.
    """
    eve_measured_bits = np.zeros(num_qubits, dtype=int)
    eve_bases = np.zeros(num_qubits, dtype=int)

    if attack_type == "Стандартный перехват-повтор":
        eve_bases = generate_random_bases(num_qubits)
        eve_measured_bits = measure_qubits(qc_from_alice.copy(), eve_bases)
        qc_to_bob = prepare_qubits(eve_measured_bits, eve_bases)

    elif attack_type == "Перехват под углом 22.5°":
        qc_copy = qc_from_alice.copy()
        for i in range(num_qubits):
            qc_copy.ry(-np.pi / 4, i)

        eve_bases = np.zeros(num_qubits, dtype=int)
        eve_measured_bits = measure_qubits(qc_copy, eve_bases)

        qc_to_bob = QuantumCircuit(num_qubits, num_qubits)
        for i in range(num_qubits):
            if eve_measured_bits[i] == 1:
                qc_to_bob.x(i)
            qc_to_bob.ry(np.pi / 4, i)

    elif attack_type == "Атака с квантовой памятью":
        combined_qc = QuantumCircuit(2 * num_qubits, 2 * num_qubits)
        combined_qc.compose(qc_from_alice, qubits=list(range(num_qubits)), clbits=list(range(num_qubits)), inplace=True)

        for i in range(num_qubits):
            combined_qc.cx(i, num_qubits + i)

        qc_to_bob = combined_qc
        eve_bases = np.zeros(num_qubits, dtype=int)
        eve_measured_bits = np.zeros(num_qubits, dtype=int)

    else:
        qc_to_bob = qc_from_alice.copy()

    return qc_to_bob, eve_bases, eve_measured_bits


def sift_key(alice_bits, alice_bases, bob_bits, bob_bases):
    """
    Классическое просеивание ключа (Sifting):
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
    После просеивания ключей выбирается случайный набор битов для оценки QBER.
    Оценочные биты исключаются из финального рабочего ключа.
    """
    sifted_len = len(alice_sifted)
    if sifted_len == 0:
        return 0.0, np.array([]), np.array([]), np.array([]) if eve_sifted is not None else None, []

    sample_size = max(1, int(np.round(sifted_len * sample_ratio)))
    if sample_size >= sifted_len:
        sample_size = max(1, sifted_len // 2)

    if sample_size == 0:
        return 0.0, alice_sifted, bob_sifted, eve_sifted, []

    sample_indices = np.random.choice(sifted_len, size=sample_size, replace=False)
    keep_indices = np.setdiff1d(np.arange(sifted_len), sample_indices)

    test_alice = alice_sifted[sample_indices]
    test_bob = bob_sifted[sample_indices]
    qber_est = np.sum(test_alice != test_bob) / float(sample_size)

    remaining_alice = alice_sifted[keep_indices]
    remaining_bob = bob_sifted[keep_indices]
    remaining_eve = eve_sifted[keep_indices] if eve_sifted is not None else None

    return qber_est, remaining_alice, remaining_bob, remaining_eve, sample_indices


def error_correction_ldpc_like(alice_key, bob_key, qber_est=0.0, manual_iterations=None):
    """
    Многоитерационный Каскадный метод коррекции ошибок (Cascade).
    """
    corrected_alice_key = alice_key.copy()
    corrected_bob_key = bob_key.copy()
    key_len = len(alice_key)

    if key_len < 2:
        return corrected_alice_key, corrected_bob_key, 0, 0

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
        nonlocal corrections_made, disclosed_parity_bits
        if hi - lo == 1:
            cur_bob_key[lo] ^= 1
            corrections_made += 1
            return
        mid = (lo + hi) // 2
        alice_parity_left = int(np.sum(corrected_alice_key[lo:mid]) % 2)
        bob_parity_left = int(np.sum(cur_bob_key[lo:mid]) % 2)
        disclosed_parity_bits += 1

        if alice_parity_left != bob_parity_left:
            bisect_and_correct(lo, mid, cur_bob_key)
        else:
            bisect_and_correct(mid, hi, cur_bob_key)

    np.random.seed(42)

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
            end = start + block_size

            alice_parity = int(np.sum(perm_alice[start:end]) % 2)
            bob_parity = int(np.sum(perm_bob[start:end]) % 2)
            disclosed_parity_bits += 1

            if alice_parity != bob_parity:
                bisect_and_correct(start, end, perm_bob)

        corrected_bob_key = perm_bob[inv_perm]

    return corrected_alice_key, corrected_bob_key, corrections_made, disclosed_parity_bits


def binary_entropy(p):
    """Шенноновская двоичная энтропия H2(p)."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * np.log2(p) - (1.0 - p) * np.log2(1.0 - p)


def toeplitz_hash(key_bits, target_length):
    """
    Универсальное хэширование на основе матриц Тёплица [Hayashi & Tsurumaru, IEEE TIT 2016].
    """
    n = len(key_bits)
    m = target_length
    if m <= 0 or n == 0:
        return np.array([], dtype=int), ""

    np.random.seed(12345)
    row = np.random.randint(0, 2, n)
    col = np.random.randint(0, 2, m)
    col[0] = row[0]

    toeplitz_matrix = np.zeros((m, n), dtype=int)
    for i in range(m):
        for j in range(n):
            if i >= j:
                toeplitz_matrix[i, j] = col[i - j]
            else:
                toeplitz_matrix[i, j] = row[j - i]

    compressed_key = np.dot(toeplitz_matrix, key_bits) % 2
    hex_str = hashlib.sha256(compressed_key.tobytes()).hexdigest()[: min(64, max(8, m // 4))]
    return compressed_key, hex_str


def privacy_amplification(key, qber_est=0.0, leaked_ec_bits=0, eve_info_fraction=0.0):
    """
    Усиление секретности с помощью универсальных матриц Тёплица.
    """
    n = len(key)
    if n == 0:
        return np.array([], dtype=int), "", 0

    h_qber = binary_entropy(qber_est)
    eavesdropper_info = max(h_qber, eve_info_fraction)
    fraction_secure = max(0.0, 1.0 - h_qber - eavesdropper_info)
    target_length = int(np.floor(n * fraction_secure - leaked_ec_bits))

    if target_length < 4 or qber_est >= 0.11:
        target_length = 0

    if target_length > 0:
        compressed_bits, hex_str = toeplitz_hash(key, target_length)
    else:
        compressed_bits, hex_str = np.array([], dtype=int), "KEY_REJECTED (QBER too high)"

    return compressed_bits, hex_str, target_length


def calculate_qber(key1, key2):
    """Расчет коэффициента битовых ошибок квантового канала (QBER)."""
    if len(key1) == 0 or len(key2) == 0 or len(key1) != len(key2):
        return 0.0
    errors = np.sum(key1 != key2)
    return errors / float(len(key1))


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class QuantumApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("BB84 Simulator & QKD Network Planner (Academic Edition - NAS Belarus)")
        self.geometry("1240x960")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Обработчик корректного закрытия окна
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Боковая панель управления
        self.sidebar = ctk.CTkFrame(self, width=320, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(
            self.sidebar, text="QKD SYSTEM & PLANNER", font=ctk.CTkFont(size=18, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(15, 10))

        # Переключатель режима работы приложения
        self.mode_label = ctk.CTkLabel(self.sidebar, text="Режим работы системы:", anchor="w")
        self.mode_label.grid(row=1, column=0, padx=20, pady=(5, 0))

        self.mode_selector = ctk.CTkSegmentedButton(
            self.sidebar, values=["BB84 Симуляция", "Планирование сетей"], command=self.toggle_mode
        )
        self.mode_selector.grid(row=2, column=0, padx=20, pady=5)
        self.mode_selector.set("BB84 Симуляция")

        # --- СЕКЦИЯ 1: Параметры BB84 Симулятора ---
        self.bb84_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.bb84_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        self.bits_label = ctk.CTkLabel(self.bb84_frame, text="Количество кубитов:", anchor="w")
        self.bits_label.pack(anchor="w", padx=10, pady=(5, 0))

        self.bits_value_label = ctk.CTkLabel(
            self.bb84_frame, text="64", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3b8ed0"
        )
        self.bits_value_label.pack(anchor="w", padx=10)

        self.bits_slider = ctk.CTkSlider(
            self.bb84_frame, from_=16, to=200, number_of_steps=23, command=self.update_slider_label
        )
        self.bits_slider.pack(fill="x", padx=10, pady=5)
        self.bits_slider.set(64)

        self.noise_label = ctk.CTkLabel(self.bb84_frame, text="Уровень шума канала (QBER-шум):", anchor="w")
        self.noise_label.pack(anchor="w", padx=10, pady=(5, 0))

        self.noise_value_label = ctk.CTkLabel(
            self.bb84_frame, text="3%", font=ctk.CTkFont(size=14, weight="bold"), text_color="#3b8ed0"
        )
        self.noise_value_label.pack(anchor="w", padx=10)

        self.noise_slider = ctk.CTkSlider(
            self.bb84_frame, from_=0, to=30, number_of_steps=30, command=self.update_noise_label
        )
        self.noise_slider.pack(fill="x", padx=10, pady=5)
        self.noise_slider.set(3)

        self.attack_label = ctk.CTkLabel(self.bb84_frame, text="Стратегия подслушивания Евы:", anchor="w")
        self.attack_label.pack(anchor="w", padx=10, pady=(5, 0))

        self.attack_combobox = ctk.CTkOptionMenu(
            self.bb84_frame,
            values=[
                "Стандартный перехват-повтор",
                "Перехват под углом 22.5°",
                "Атака с квантовой памятью",
            ],
        )
        self.attack_combobox.pack(fill="x", padx=10, pady=5)
        self.attack_combobox.set("Стандартный перехват-повтор")

        self.eve_switch = ctk.CTkSwitch(self.bb84_frame, text="Присутствие Евы (Eve)")
        self.eve_switch.pack(anchor="w", padx=10, pady=10)

        # --- СЕКЦИЯ 2: Параметры планирования квантовых сетей ---
        self.planner_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")

        self.len_label = ctk.CTkLabel(self.planner_frame, text="Длина ВОЛС L (км):", anchor="w")
        self.len_label.pack(anchor="w", padx=10, pady=(5, 0))
        self.len_entry = ctk.CTkEntry(self.planner_frame)
        self.len_entry.insert(0, "50.0")
        self.len_entry.pack(fill="x", padx=10, pady=2)

        self.atten_label = ctk.CTkLabel(self.planner_frame, text="Затухание α (дБ/км):", anchor="w")
        self.atten_label.pack(anchor="w", padx=10, pady=(5, 0))
        self.atten_entry = ctk.CTkEntry(self.planner_frame)
        self.atten_entry.insert(0, "0.20")
        self.atten_entry.pack(fill="x", padx=10, pady=2)

        self.det_label = ctk.CTkLabel(self.planner_frame, text="Эффективность детектора η_det:", anchor="w")
        self.det_label.pack(anchor="w", padx=10, pady=(5, 0))
        self.det_entry = ctk.CTkEntry(self.planner_frame)
        self.det_entry.insert(0, "0.25")
        self.det_entry.pack(fill="x", padx=10, pady=2)

        self.dark_label = ctk.CTkLabel(self.planner_frame, text="Темновой отсчет P_dark (на имп.):", anchor="w")
        self.dark_label.pack(anchor="w", padx=10, pady=(5, 0))
        self.dark_entry = ctk.CTkEntry(self.planner_frame)
        self.dark_entry.insert(0, "1e-6")
        self.dark_entry.pack(fill="x", padx=10, pady=2)

        self.freq_label = ctk.CTkLabel(self.planner_frame, text="Частота лазера f (МГц):", anchor="w")
        self.freq_label.pack(anchor="w", padx=10, pady=(5, 0))
        self.freq_entry = ctk.CTkEntry(self.planner_frame)
        self.freq_entry.insert(0, "100.0")
        self.freq_entry.pack(fill="x", padx=10, pady=2)

        # Кнопки действий
        self.run_button = ctk.CTkButton(
            self.sidebar,
            text="ЗАПУСТИТЬ РАСЧЕТ",
            command=self.start_simulation_thread,
            font=ctk.CTkFont(weight="bold"),
        )
        self.run_button.grid(row=5, column=0, padx=20, pady=10)

        self.clear_button = ctk.CTkButton(
            self.sidebar, text="Очистить логи", fg_color="transparent", border_width=2, command=self.clear_logs
        )
        self.clear_button.grid(row=6, column=0, padx=20, pady=5)

        self.disclaimer_label = ctk.CTkLabel(
            self.sidebar,
            text="Модель объединяет квантовые вентили BB84 с физической моделью ВОЛС, детекторами SPAD/SNSPD и пределом PLOB.",
            font=ctk.CTkFont(size=9, slant="italic"),
            text_color="#ffae42",
            wraplength=270,
        )
        self.disclaimer_label.grid(row=7, column=0, padx=20, pady=10)

        self.author_label = ctk.CTkLabel(
            self.sidebar,
            text="© 2026 Roman Maksimov\nНаучный рецензент: д.ф.-м.н. А.Б. Михалычев\nИнститут физики НАН Беларуси",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color="gray",
        )
        self.author_label.grid(row=8, column=0, padx=20, pady=(15, 10), sticky="s")

        # Главная область вывода
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(1, weight=1)

        # Информационные карточки
        self.metrics_frame = ctk.CTkFrame(self.main_content, height=100)
        self.metrics_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.metrics_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.qber_title_label, self.qber_card = self.create_metric_card(
            self.metrics_frame, "QBER (Оценка)", "0.00", 0
        )
        self.status_title_label, self.status_card = self.create_metric_card(
            self.metrics_frame, "Статус канала", "Ожидание", 1
        )
        self.key_len_title_label, self.key_len_card = self.create_metric_card(
            self.metrics_frame, "Длина секретного ключа", "0", 2
        )

        # Лог-терминал
        self.textbox = ctk.CTkTextbox(self.main_content, font=ctk.CTkFont(family="Consolas", size=12))
        self.textbox.grid(row=1, column=0, sticky="nsew")

    def toggle_mode(self, value):
        if value == "BB84 Симуляция":
            self.planner_frame.grid_forget()
            self.bb84_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
            self.run_button.configure(text="ЗАПУСТИТЬ ПРОТОКОЛ")
            self.key_len_title_label.configure(text="Длина секретного ключа")
        else:
            self.bb84_frame.grid_forget()
            self.planner_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
            self.run_button.configure(text="РАССЧИТАТЬ СЕТЬ QKD")
            self.key_len_title_label.configure(text="Скорость SKR (бит/с)")

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
        return t_label, v_label

    def log(self, message):
        if self.winfo_exists():
            self.after(0, lambda: self._safe_log(message))

    def _safe_log(self, message):
        if self.winfo_exists() and hasattr(self, "textbox"):
            self.textbox.insert("end", f"{message}\n")
            self.textbox.see("end")

    def clear_logs(self):
        self.textbox.delete("1.0", "end")
        self.qber_card.configure(text="0.00", text_color="white")
        self.status_card.configure(text="Ожидание", text_color="white")
        self.key_len_card.configure(text="0")

    def start_simulation_thread(self):
        self.run_button.configure(state="disabled")
        threading.Thread(target=self.run_execution, daemon=True).start()

    def run_execution(self):
        mode = self.mode_selector.get()
        if mode == "BB84 Симуляция":
            self.run_simulation()
        else:
            self.run_network_planning()

    def run_network_planning(self):
        try:
            distance_km = float(self.len_entry.get())
            attenuation_db = float(self.atten_entry.get())
            det_efficiency = float(self.det_entry.get())
            dark_count_rate = float(self.dark_entry.get())
            freq_mhz = float(self.freq_entry.get())
            repetition_rate_hz = freq_mhz * 1e6

            self.log("=== РЕЖИМ ПЛАНИРОВАНИЯ И АНАЛИЗА СЕТЕЙ QKD ===")
            self.log(f"Параметры линии: Длина L = {distance_km} км | Затухание alpha = {attenuation_db} дБ/км")
            self.log(
                f"Детектор (SPAD/SNSPD): Эффективность eta = {det_efficiency*100:.1f}% | Темновой отсчет P_dark = {dark_count_rate}"
            )
            self.log(f"Квантовый излучатель: Частота f = {freq_mhz} МГц\n")

            # Расчет физических параметров
            trans = calculate_fiber_transmission(distance_km, attenuation_db)
            qber_phys, snr, p_click = calculate_physical_qber(
                distance_km, attenuation_db, det_efficiency, dark_count_rate
            )
            skr, _, _, net_fraction = calculate_secret_key_rate(
                distance_km, repetition_rate_hz, attenuation_db, det_efficiency, dark_count_rate
            )

            self.log(f"1. Пропускание волокна T:          {trans:.6f} ({10*np.log10(trans):.2f} дБ затухания)")
            self.log(f"2. Соотношение сигнал/шум (SNR):   {snr:.2f}")
            self.log(f"3. Физический QBER(phys):           {qber_phys*100:.2f}%")
            self.log(f"4. Полезная доля ключа (r_net):    {net_fraction*100:.2f}%")
            self.log(f"5. Скорость секретного ключа SKR:  {skr/1000.0:.2f} кбит/с ({skr:.0f} бит/с)")

            status_text = "БЕЗОПАСНО" if qber_phys < 0.11 else "ЛИНИЯ НЕЭФФЕКТИВНА"
            self.after(0, lambda: self.update_ui_results(qber_phys, f"{skr/1000.0:.1f} кбит/с", status_text))

            # Построение графического анализа в отдельном окне
            self.after(
                0,
                lambda: self.show_planner_plots(
                    attenuation_db, det_efficiency, dark_count_rate, repetition_rate_hz, distance_km
                ),
            )

        except Exception as e:
            self.log(f"ОШИБКА ПЛАНИРОВАНИЯ СЕТИ: {str(e)}")
        finally:
            self.after(0, lambda: self.run_button.configure(state="normal"))

    def show_planner_plots(self, alpha, eta, p_dark, f_hz, current_L):
        try:
            plt.clf()
            plot_window = ctk.CTkToplevel(self)
            plot_window.title("Анализ сетей QKD: Зависимость SKR и QBER от расстояния ВОЛС")
            plot_window.geometry("900x600")
            plot_window.after(150, lambda: plot_window.focus())

            distances = np.linspace(0, 150, 100)
            skr_list = []
            qber_list = []
            plob_list = []

            for d in distances:
                s, q, _, _ = calculate_secret_key_rate(d, f_hz, alpha, eta, p_dark)
                T = calculate_fiber_transmission(d, alpha)
                # Предел Пирандолы-Лоренцани-Оттавиани-Бэйнса (PLOB bound)
                plob_bound = -np.log2(1.0 - T) * f_hz * 0.5 if T < 1.0 else 0

                skr_list.append(s / 1000.0)  # кбит/с
                qber_list.append(q * 100.0)
                plob_list.append(plob_bound / 1000.0)

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6))

            # График 1: Скорость генерации ключа SKR
            ax1.plot(distances, skr_list, "b-", label="Расчетная SKR (кбит/с)", linewidth=2)
            ax1.plot(distances, plob_list, "k--", label="Теоретический предел PLOB", alpha=0.6)
            ax1.axvline(x=current_L, color="r", linestyle=":", label=f"Текущая дистанция L={current_L}км")
            ax1.set_yscale("log")
            ax1.set_ylabel("SKR (кбит/с) [Лог-масштаб]")
            ax1.set_title("Скорость передачи секретного ключа (SKR) vs Длина ВОЛС")
            ax1.grid(True, which="both", ls="--", alpha=0.5)
            ax1.legend()

            # График 2: QBER vs Дистанция
            ax2.plot(distances, qber_list, "r-", label="Физический QBER (%)", linewidth=2)
            ax2.axhline(y=11.0, color="g", linestyle="--", label="Порог Шора-Прескилла (11%)")
            ax2.axvline(x=current_L, color="r", linestyle=":")
            ax2.set_xlabel("Длина оптического волокна L (км)")
            ax2.set_ylabel("QBER (%)")
            ax2.set_title("Зависимость уровня ошибок QBER от длины линии связи")
            ax2.grid(True, ls="--", alpha=0.5)
            ax2.legend()

            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=plot_window)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=15, pady=15)

            def on_close():
                plt.close(fig)
                if canvas.get_tk_widget().winfo_exists():
                    canvas.get_tk_widget().destroy()
                if plot_window.winfo_exists():
                    plot_window.destroy()

            plot_window.protocol("WM_DELETE_WINDOW", on_close)

        except Exception as e:
            self.log(f"Ошибка визуализации графиков планировщика: {e}")

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

            scenario_num = "2" if introduce_eve else "1"
            scenario_text = (
                f"С ЕВОЙ (Атака: {attack_strategy})" if introduce_eve else "БЕЗ ЕВЫ (Чистый/зашумленный канал)"
            )
            self.log(f"\n=== СЦЕНАРИЙ {scenario_num}: Квантовый канал {scenario_text} ===")
            self.log(f"--- Параметры: Излучено кубитов: {num_bits} | Аппаратный Шум: {noise_prob*100:.1f}% ---\n")

            # 1. Этап Алисы
            alice_bits = generate_random_bits(num_bits)
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

                if noise_prob > 0:
                    qc_to_bob = apply_channel_noise(qc_to_bob, noise_prob)
            else:
                qc_to_bob = alice_circuit.copy()

            # 3. Измерение Боба
            bob_bases = generate_random_bases(num_bits)
            bob_measured_bits = measure_qubits(qc_to_bob, bob_bases)

            self.log(f"[Боб]:  Измерил биты:         {bob_measured_bits}")
            self.log(f"[Боб]:  Использовал базисы:   {bob_bases}")

            # --- ПОСЛЕ СРАВНЕНИЯ БАЗИСОВ ---
            sifted_alice_key, sifted_bob_key, matching_indices = sift_key(
                alice_bits, alice_bases, bob_measured_bits, bob_bases
            )

            self.log("\n--- ЭТАП 1: Классическое просеивание (Sifting) ---")
            self.log(f"Совпавшие индексы базисов:  {matching_indices}")
            self.log(f"Просеянный ключ Алисы:      {sifted_alice_key}")
            self.log(f"Просеянный ключ Боба:        {sifted_bob_key}")

            if introduce_eve and attack_strategy == "Атака с квантовой памятью":
                eve_bases = alice_bases.copy()
                eve_measured_bits = measure_qubits(qc_to_bob, eve_bases)
                self.log(f"[Ева→Память]: Провела измерение ancilla-кубитов ПОСЛЕ объявления базисов.")

            sifted_eve_key = None
            if introduce_eve:
                sifted_eve_key = np.array([eve_measured_bits[idx] for idx in matching_indices])

            # Оценка QBER и выборка битов
            self.log("\n--- Оценка QBER и отброс выборочных битов ---")
            qber_est, remaining_alice, remaining_bob, remaining_eve, test_indices = estimate_qber_and_sample(
                sifted_alice_key, sifted_bob_key, sifted_eve_key, sample_ratio=0.25
            )
            self.log(f"Оцененное значение QBER:     {qber_est:.4f} ({qber_est*100:.1f}%)")
            self.log(f"Исключено проверочных бит:   {len(test_indices)} (удалены из финального ключа)")
            self.log(f"Остаточный просеянный ключ (Алиса): {remaining_alice}")
            self.log(f"Остаточный просеянный ключ (Боб):   {remaining_bob}")

            # Коррекция ошибок Cascade
            self.log("\n--- ЭТАП 2: Многоитерационная коррекция ошибок Cascade ---")
            corrected_alice, corrected_bob, err_count, leaked_ec_bits = error_correction_ldpc_like(
                remaining_alice, remaining_bob, qber_est=qber_est
            )
            final_qber = calculate_qber(corrected_alice, corrected_bob)
            self.log(f"Исправлено ошибок у Боба:    {err_count}")
            self.log(f"Разглашено бит чётности (leak_EC): {leaked_ec_bits}")
            self.log(f"Согласованный ключ Алисы:    {corrected_alice}")
            self.log(f"Согласованный ключ Боба:     {corrected_bob}")
            self.log(f"Остаточная неисправленная ошибка: {final_qber:.4f}")

            # Усиление секретности матрицами Тёплица
            self.log("\n--- ЭТАП 3: Усиление секретности матрицами Тёплица ---")
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

            if introduce_eve and remaining_eve is not None and len(remaining_eve) > 0:
                self.log("\n--- АНАЛИЗ ИНФОРМАЦИОННОЙ БЕЗОПАСНОСТИ ЕВЫ ---")
                eve_raw_corr = np.sum(remaining_eve == remaining_alice) / float(len(remaining_alice))
                self.log(f"1. Сходство ключа Евы ДО усиления секретности: {eve_raw_corr*100:.1f}%")

                if final_len > 0:
                    amp_eve_bits, amp_eve_hex, _ = privacy_amplification(
                        remaining_eve, qber_est=qber_est, leaked_ec_bits=leaked_ec_bits, eve_info_fraction=eve_info_frac
                    )
                    eve_final_corr = (
                        np.sum(amp_eve_bits == amp_alice_bits) / float(final_len)
                        if len(amp_eve_bits) == final_len
                        else 0.5
                    )
                    self.log(
                        f"2. Сходство ключа Евы ПОСЛЕ универсального хэширования Тёплица: {eve_final_corr*100:.1f}%"
                    )

            # --- ВЫВОДЫ ---
            self.log("\n--- АНАЛИТИЧЕСКИЕ ВЫВОДЫ ---")
            if qber_est >= 0.11:
                status_text = "ОБНАРУЖЕН ВЗЛОМ!"
                self.log(
                    f"!!! {status_text} QBER ({qber_est*100:.1f}%) выше предела Шора-Прескилла (11%). Ключ СКОМПРОМЕТИРОВАН! !!!"
                )
            else:
                status_text = "БЕЗОПАСНО"
                self.log(f"✓ {status_text}: QBER ({qber_est*100:.1f}%) в пределах нормы (<11%). Ключ успешно распределен.")

            self.after(0, lambda: self.update_ui_results(qber_est, f"{final_len if keys_match else 0} бит", status_text))

            # Визуализация физической квантовой схемы
            self.log("\nПодготовка интерактивной схемы...")
            vis_count = min(4, num_bits)
            vis_qc = QuantumCircuit(vis_count, vis_count)
            for i in range(vis_count):
                if alice_bits[i] == 1:
                    vis_qc.x(i)
                if alice_bases[i] == 1:
                    vis_qc.h(i)
            vis_qc.barrier()
            for i in range(vis_count):
                if bob_bases[i] == 1:
                    vis_qc.h(i)
                vis_qc.measure(i, i)

            self.after(0, lambda: self.show_plot(vis_qc, vis_count))

        except Exception as e:
            self.log(f"ОШИБКА СИМУЛЯЦИИ: {str(e)}")
        finally:
            self.after(0, lambda: self.run_button.configure(state="normal"))

    def show_plot(self, qc, count):
        """
        Интеграция холста Matplotlib в архитектуру CustomTkinter.
        """
        try:
            plt.clf()
            plot_window = ctk.CTkToplevel(self)
            plot_window.title("Квантовая схема протокола BB84 (Физический уровень)")
            plot_window.geometry("850x450")
            plot_window.after(150, lambda: plot_window.focus())

            fig, ax = plt.subplots(figsize=(8, 4))
            qc.draw(output="mpl", style={"name": "bw"}, ax=ax)
            ax.set_title(
                f"Визуализация квантовых вентилей (первые {count} кубитов)\n"
                f"Алиса (Генерация) → Квантовый канал → Боб (Измерение)"
            )
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=plot_window)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=15, pady=15)

            def on_close():
                plt.close(fig)
                if canvas.get_tk_widget().winfo_exists():
                    canvas.get_tk_widget().destroy()
                if plot_window.winfo_exists():
                    plot_window.destroy()

            plot_window.protocol("WM_DELETE_WINDOW", on_close)

        except Exception as e:
            self.log(f"Не удалось отрисовать схему: {e}")

    def update_ui_results(self, qber, key_str, status):
        if not self.winfo_exists():
            return

        self.qber_card.configure(text=f"{qber:.4f}")
        self.key_len_card.configure(text=str(key_str))

        if "ВЗЛОМ" in status or "НЕЭФФЕКТИВНА" in status:
            self.qber_card.configure(text_color="#ff4b4b")
            self.status_card.configure(text=status, text_color="#ff4b4b")
        else:
            self.qber_card.configure(text_color="#47d147")
            self.status_card.configure(text=status, text_color="#47d147")

    def on_closing(self):
        plt.close("all")
        self.destroy()


if __name__ == "__main__":
    app = QuantumApp()
    app.mainloop()
