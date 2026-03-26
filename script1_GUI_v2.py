import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
import customtkinter as ctk
from tkinter import messagebox
import threading
import matplotlib.pyplot as plt


def generate_random_bits(num_bits):
    """Генерирует случайные биты (0 или 1)."""
    return np.random.randint(0, 2, num_bits)


def generate_random_bases(num_bits):
    """Генерирует случайные базисы (0 для стандартного, 1 для диагонального)."""
    return np.random.randint(0, 2, num_bits)


def prepare_qubits(bits, bases):
    """Алиса: Подготавливает кубиты."""
    qc = QuantumCircuit(len(bits), len(bits))
    for i in range(len(bits)):
        if bits[i] == 1:
            qc.x(i)
        if bases[i] == 1:
            qc.h(i)
    return qc


def measure_qubits(qc_to_measure, bases):
    """Боб: Измеряет кубиты в выбранных базисах."""
    simulator = AerSimulator()
    qc_copy = qc_to_measure.copy()
    for i in range(len(bases)):
        if bases[i] == 1:
            qc_copy.h(i)
        qc_copy.measure(i, i)

    job = simulator.run(qc_copy, shots=1)
    result = job.result().get_counts()

    measured_bits_str = list(result.keys())[0]
    measured_bits = np.array([int(b) for b in measured_bits_str[::-1]])
    return measured_bits


def eavesdrop_on_qubits(qc_from_alice, num_qubits):
    """Ева: Перехват и повторная пересылка (Intersept-Resend)."""
    eve_bases = generate_random_bases(num_qubits)
    eve_measured_bits = measure_qubits(qc_from_alice, eve_bases)
    qc_to_bob = prepare_qubits(eve_measured_bits, eve_bases)
    return qc_to_bob, eve_bases


def sift_key(alice_bits, alice_bases, bob_bits, bob_bases):
    """Сравнение базисов и формирование просеянного ключа."""
    final_alice_key = []
    final_bob_key = []
    matching_indices = []
    for i in range(len(alice_bits)):
        if alice_bases[i] == bob_bases[i]:
            final_alice_key.append(alice_bits[i])
            final_bob_key.append(bob_bits[i])
            matching_indices.append(i)
    return np.array(final_alice_key), np.array(final_bob_key), matching_indices


def calculate_qber(key1, key2):
    """Расчет частоты ошибок в битах (QBER)."""
    if len(key1) == 0 or len(key2) == 0:
        return 0.0
    errors = np.sum(key1 != key2)
    return errors / len(key1)


# --- ИНТЕРФЕЙС С ИНФОРМАТИВНЫМ ВЫВОДОМ ---

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class QuantumApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("BB84 Simulator - Maksimov R.V., 9B class")
        self.geometry("1100x850")

        # Настройка сетки
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Боковая панель
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="BB84 SIMULATOR", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.bits_label = ctk.CTkLabel(self.sidebar, text="Количество кубитов:", anchor="w")
        self.bits_label.grid(row=1, column=0, padx=20, pady=(10, 0))

        self.bits_value_label = ctk.CTkLabel(self.sidebar, text="32", font=ctk.CTkFont(size=16, weight="bold"),
                                             text_color="#3b8ed0")
        self.bits_value_label.grid(row=2, column=0, padx=20, pady=(0, 5))

        self.bits_slider = ctk.CTkSlider(self.sidebar, from_=4, to=100, number_of_steps=24,
                                         command=self.update_slider_label)
        self.bits_slider.grid(row=3, column=0, padx=20, pady=10)
        self.bits_slider.set(32)

        self.eve_switch = ctk.CTkSwitch(self.sidebar, text="Присутствие Евы (Eve)")
        self.eve_switch.grid(row=4, column=0, padx=20, pady=20)

        self.run_button = ctk.CTkButton(self.sidebar, text="ЗАПУСТИТЬ ПРОТОКОЛ", command=self.start_simulation_thread,
                                        font=ctk.CTkFont(weight="bold"))
        self.run_button.grid(row=5, column=0, padx=20, pady=10)

        self.clear_button = ctk.CTkButton(self.sidebar, text="Очистить логи", fg_color="transparent", border_width=2,
                                          command=self.clear_logs)
        self.clear_button.grid(row=6, column=0, padx=20, pady=10)

        self.author_label = ctk.CTkLabel(self.sidebar,
                                         text="© 2026 Roman Maksimov\nSchool №2, Postavy",
                                         font=ctk.CTkFont(size=10, slant="italic"),
                                         text_color="gray")
        self.author_label.grid(row=8, column=0, padx=20, pady=(100, 10), sticky="s")

        # Основной фрейм
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(1, weight=1)

        # Метрики
        self.metrics_frame = ctk.CTkFrame(self.main_content, height=100)
        self.metrics_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.metrics_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.qber_card = self.create_metric_card(self.metrics_frame, "QBER (Ошибки)", "0.00", 0)
        self.status_card = self.create_metric_card(self.metrics_frame, "Статус канала", "Ожидание", 1)
        self.key_len_card = self.create_metric_card(self.metrics_frame, "Длина ключа", "0", 2)

        # Текстовое поле
        self.textbox = ctk.CTkTextbox(self.main_content, font=ctk.CTkFont(family="Consolas", size=13))
        self.textbox.grid(row=1, column=0, sticky="nsew")

    def update_slider_label(self, value):
        self.bits_value_label.configure(text=str(int(value)))

    def create_metric_card(self, master, title, value, col):
        frame = ctk.CTkFrame(master)
        frame.grid(row=0, column=col, padx=10, pady=10, sticky="nsew")
        t_label = ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=12, slant="italic"))
        t_label.pack(pady=(5, 0))
        v_label = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=24, weight="bold"))
        v_label.pack(pady=(0, 5))
        return v_label

    def log(self, message):
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
            introduce_eve = self.eve_switch.get()

            # Формирование заголовка сценария
            self.log("Разработчик системы: Максимов Роман Викторович")
            self.log("-" * 40)
            scenario_num = "2" if introduce_eve else "1"
            scenario_text = "С ЕВОЙ" if introduce_eve else "БЕЗ ЕВЫ"
            self.log(f"\n=== СЦЕНАРИЙ {scenario_num}: Квантовый канал {scenario_text} ===")
            self.log(f"--- Симуляция BB84 для {num_bits} кубитов (Ева: {'Да' if introduce_eve else 'Нет'}) ---")

            # --- ХОД ПРОТОКОЛА ---
            alice_bits = generate_random_bits(num_bits)
            alice_bases = generate_random_bases(num_bits)
            self.log(f"Алиса отправила биты:  {alice_bits}")
            self.log(f"Базисы Алисы:          {alice_bases}")

            alice_circuit = prepare_qubits(alice_bits, alice_bases)

            if introduce_eve:
                qc_to_bob, eve_bases = eavesdrop_on_qubits(alice_circuit, num_bits)
                self.log(f"Ева перехватила и измерила, базисы Евы: {eve_bases}")
            else:
                qc_to_bob = alice_circuit.copy()

            bob_bases = generate_random_bases(num_bits)
            bob_measured_bits = measure_qubits(qc_to_bob, bob_bases)
            self.log(f"Боб измерил биты:      {bob_measured_bits}")
            self.log(f"Базисы Боба:           {bob_bases}")

            # --- ПОСЛЕ СРАВНЕНИЯ БАЗИСОВ ---
            sifted_alice_key, sifted_bob_key, matching_indices = sift_key(alice_bits, alice_bases, bob_measured_bits,
                                                                          bob_bases)
            qber = calculate_qber(sifted_alice_key, sifted_bob_key)

            self.log("\n--- После сравнения базисов ---")
            self.log(f"Совпавшие индексы:      {matching_indices}")
            self.log(f"Отобранный ключ Алисы: {sifted_alice_key}")
            self.log(f"Отобранный ключ Боба:  {sifted_bob_key}")
            self.log(f"Частота ошибок (QBER): {qber:.2f}")

            # --- ВЫВОДЫ ---
            if qber > 0.1:
                self.log("!!! ОБНАРУЖЕНА ЕВА! Попытка взлома. Ключ не будет использован. !!!")
            else:
                self.log("Квантовый канал чист. Ключ успешно сформирован и может быть использован.")

            self.log("\n--- Выводы для Отчета ---")
            self.log("Внедрение Евы приводит к росту QBER, что служит индикатором компрометации.")
            self.log("Это прямое доказательство того, что квантовая криптография позволяет обнаружить взлом.")

            self.after(0, lambda: self.update_ui_results(qber, len(sifted_alice_key)))

            # Визуализация
            self.log("\nПодготовка итоговой схемы...")
            vis_count = min(5, num_bits)
            vis_qc = QuantumCircuit(vis_count, vis_count)
            for i in range(vis_count):
                if alice_bits[i] == 1: vis_qc.x(i)
                if alice_bases[i] == 1: vis_qc.h(i)
            vis_qc.barrier()
            for i in range(vis_count):
                if bob_bases[i] == 1: vis_qc.h(i)
                vis_qc.measure(i, i)

            self.after(0, lambda: self.show_plot(vis_qc, vis_count))

        except Exception as e:
            self.log(f"ОШИБКА: {str(e)}")
        finally:
            self.after(0, lambda: self.run_button.configure(state="normal"))

    def show_plot(self, qc, count):
        try:
            plt.figure(figsize=(10, 6))
            qc.draw(output='mpl', style={'name': 'bw'}, ax=plt.gca())
            plt.title(f"Визуализация процесса (первые {count} кубитов)\nАлиса (гейты) -> Боб (измерения)")
            plt.tight_layout()
            plt.show()
        except Exception as e:
            self.log(f"Не удалось отрисовать схему: {e}")

    def update_ui_results(self, qber, key_len):
        self.qber_card.configure(text=f"{qber:.2f}")
        self.key_len_card.configure(text=str(key_len))
        if qber > 0.1:
            self.qber_card.configure(text_color="#ff4b4b")
            self.status_card.configure(text="ВЗЛОМ!", text_color="#ff4b4b")
        else:
            self.qber_card.configure(text_color="#47d147")
            self.status_card.configure(text="БЕЗОПАСНО", text_color="#47d147")


if __name__ == "__main__":
    app = QuantumApp()
    app.mainloop()