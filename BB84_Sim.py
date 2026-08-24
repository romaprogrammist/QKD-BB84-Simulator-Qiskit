# ==============================================================================
# © 2025-2026 Максимов Роман Викторович. Все права защищены.
# © 2025-2026 Maksimov Roman Viktorovich. All rights reserved.
# Проект: QKD-BB84-Simulator-Qiskit (Академическая Версия v3.1)
#
# Данное программное обеспечение и его исходный код являются конфиденциальной
# интеллектуальной собственностью автора. Допуск предоставлен исключительно 
# для целей академического аудита и рецензирования. Любое несанкционированное 
# копирование, распространение, модификация или реверс-инжиниринг запрещены.
# Подробные условия использования изложены в файле LICENSE.
# ==============================================================================
# Полный исходный код симулятора BB84 (устаревшая версия новая версия в интерфейсном решении)
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator  

def generate_random_bits(num_bits):
    """Генерирует случайные биты (0 или 1)."""
    return np.random.randint(0, 2, num_bits)


def generate_random_bases(num_bits):
    """Генерирует случайные базисы (0 для стандартного, 1 для диагонального)."""
    return np.random.randint(0, 2, num_bits)


def prepare_qubits(bits, bases):
    """
    Алиса: Подготавливает кубиты в соответствии с битами и выбранными базисами.
    Базис 0 (стандартный): |0> или |1>
    Базис 1 (диагональный): |+> или |-> (получается применением гейта Адамара к |0> или |1>)
    """
    qc = QuantumCircuit(len(bits), len(bits))
    for i in range(len(bits)):
        if bits[i] == 1:
            qc.x(i)  # Применяем гейт X, чтобы превратить |0> в |1>
        if bases[i] == 1:
            qc.h(i)  # Применяем гейт Адамара для диагонального базиса
    return qc


def measure_qubits(qc_to_measure, bases):
    """
    Боб/Ева: Измеряет кубиты в соответствии с выбранными базисами.
    Возвращает измеренные биты.
    """
    simulator = AerSimulator()
    qc_copy = qc_to_measure.copy()
    for i in range(len(bases)):
        if bases[i] == 1:
            qc_copy.h(i)  # Переключаемся в стандартный базис для измерения, если изначально был диагональный
        qc_copy.measure(i, i)  # Измеряем кубит и записываем результат в классический бит

    # Внимание: для больших num_qubits, transpile может быть медленным или вызывать ошибки
    # Если проблема повторится, можно попробовать убрать transpile для AerSimulator,
    # т.к. он часто может выполнять схемы напрямую без явной транспиляции.
    # Но для демонстрации и соответствия реальным процессам, пока оставим.
    compiled_circuit = transpile(qc_copy, simulator)
    job = simulator.run(compiled_circuit, shots=1)
    result = job.result().get_counts(compiled_circuit)

    measured_bits_str = list(result.keys())[0]
    measured_bits = np.array([int(b) for b in measured_bits_str[::-1]])
    return measured_bits


def eavesdrop_on_qubits(qc_from_alice, num_qubits):
    """
    Ева: Перехватывает кубиты, измеряет их в случайно выбранных базисах,
    а затем подготавливает новые кубиты на основе своих измерений
    и отправляет их Бобу.
    Возвращает схему с "испорченными" кубитами и базисы Евы.
    """
    eve_bases = generate_random_bases(num_qubits)
    eve_measured_bits = measure_qubits(qc_from_alice, eve_bases)

    qc_to_bob = prepare_qubits(eve_measured_bits, eve_bases)

    return qc_to_bob, eve_bases


def sift_key(alice_bits, alice_bases, bob_bits, bob_bases):
    """
    Алиса и Боб публично сравнивают свои базисы.
    Сохраняют только те биты, где базисы совпали.
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


def calculate_qber(key1, key2):
    """
    Вычисляет частоту битовых ошибок (Quantum Bit Error Rate - QBER)
    между двумя ключами.
    """
    if len(key1) == 0 or len(key2) == 0:
        return 0.0

    errors = np.sum(key1 != key2)
    return errors / len(key1)


def run_bb84_simulation(num_bits, introduce_eve=False):
    """
    Запускает полную симуляцию протокола BB84.
    """
    print(f"\n--- Симуляция BB84 для {num_bits} кубитов (Ева: {'Да' if introduce_eve else 'Нет'}) ---")

    alice_bits = generate_random_bits(num_bits)
    alice_bases = generate_random_bases(num_bits)
    print(f"Алиса отправила биты:  {alice_bits}")
    print(f"Базисы Алисы:          {alice_bases}")

    alice_circuit = prepare_qubits(alice_bits, alice_bases)

    if introduce_eve:
        qc_to_bob, eve_bases = eavesdrop_on_qubits(alice_circuit, num_bits)
        print(f"Ева перехватила и измерила, базисы Евы: {eve_bases}")
    else:
        qc_to_bob = alice_circuit.copy()

    bob_bases = generate_random_bases(num_bits)
    bob_measured_bits = measure_qubits(qc_to_bob, bob_bases)
    print(f"Боб измерил биты:      {bob_measured_bits}")
    print(f"Базисы Боба:           {bob_bases}")

    sifted_alice_key, sifted_bob_key, matching_indices = sift_key(alice_bits, alice_bases, bob_measured_bits, bob_bases)

    print(f"\n--- После сравнения базисов ---")
    print(f"Совпавшие индексы:     {matching_indices}")
    print(f"Отобранный ключ Алисы: {sifted_alice_key}")
    print(f"Отобранный ключ Боба:  {sifted_bob_key}")

    qber = calculate_qber(sifted_alice_key, sifted_bob_key)
    print(f"Частота ошибок (QBER): {qber:.2f}")

    if qber > 0.1:
        print("!!! ОБНАРУЖЕНА ЕВА! Попытка взлома. Ключ не будет использован. !!!")
    else:
        print("Квантовый канал чист. Ключ может быть использован.")

    return qber, sifted_alice_key, sifted_bob_key


if __name__ == "__main__":
    num_qubits_to_send = 20  

    print("\n\n=== СЦЕНАРИЙ 1: Квантовый канал БЕЗ ЕВЫ ===")
    qber_no_eve, key_alice_no_eve, key_bob_no_eve = run_bb84_simulation(num_qubits_to_send, introduce_eve=False)

    print("\n\n=== СЦЕНАРИЙ 2: Квантовый канал С ЕВОЙ ===")
    qber_with_eve, key_alice_with_eve, key_bob_with_eve = run_bb84_simulation(num_qubits_to_send, introduce_eve=True)

    print("\n--- Сводка результатов ---")
    print(f"QBER без Евы: {qber_no_eve:.2f}")
    print(f"QBER с Евой:  {qber_with_eve:.2f}")

    if qber_with_eve > qber_no_eve + 0.05:
        print(
            "\n**Практическое доказательство:** Вмешательство Евы значительно увеличивает частоту ошибок, что позволяет Алисе и Бобу обнаружить её присутствие.")
    else:
        print(
            "\nРезультаты QBER могут варьироваться из-за случайности. Попробуйте запустить несколько раз или с большим количеством кубитов.")

    print("\n--- Выводы для Отчета ---")
    print(
        "Этот код демонстрирует фундаментальный принцип безопасности QKD: любая попытка измерения квантового состояния подслушивателем (Евой) неизбежно вносит возмущения, которые могут быть обнаружены законными участниками.")
    print("Внедрение Евы приводит к росту QBER, что служит индикатором компрометации канала.")
    print(
        "Это прямое доказательство того, что, в отличие от классической криптографии, квантовая криптография позволяет не только зашифровать данные, но и *обнаружить* попытку взлома.")
    input()
