import threading
import time

# ── 1. CON RACE CONDITION ────────────────────────────────────────────────────
print("=" * 50)
print("SIN LOCK (race condition)")
print("=" * 50)

saldo_rc = 1000

def retirar_sin_lock(monto):
    global saldo_rc
    if saldo_rc >= monto:
        time.sleep(0.001)   # simular procesamiento
        saldo_rc -= monto
        print(f"  Retiro de ${monto} exitoso.  Saldo: ${saldo_rc}")
    else:
        print(f"  Saldo insuficiente para retirar ${monto}. Saldo: ${saldo_rc}")

hilos = [threading.Thread(target=retirar_sin_lock, args=(200,)) for _ in range(10)]
for h in hilos: h.start()
for h in hilos: h.join()

print(f"\n  Saldo final (esperado >= 0): ${saldo_rc}")
print(f"  {'⚠ SALDO NEGATIVO — race condition detectada!' if saldo_rc < 0 else '(sin problema esta vez, intentá de nuevo)'}")

# ── 2. CORREGIDO CON LOCK ────────────────────────────────────────────────────
print()
print("=" * 50)
print("CON LOCK (corregido)")
print("=" * 50)

saldo_lock = 1000
lock = threading.Lock()

def retirar_con_lock(monto):
    global saldo_lock
    with lock:                      # solo un hilo entra a la vez
        if saldo_lock >= monto:
            time.sleep(0.001)
            saldo_lock -= monto
            print(f"  Retiro de ${monto} exitoso.  Saldo: ${saldo_lock}")
        else:
            print(f"  Saldo insuficiente para retirar ${monto}. Saldo: ${saldo_lock}")

hilos = [threading.Thread(target=retirar_con_lock, args=(200,)) for _ in range(10)]
for h in hilos: h.start()
for h in hilos: h.join()

print(f"\n  Saldo final (esperado >= 0): ${saldo_lock}")
print(f"  {'✓ Saldo protegido correctamente.' if saldo_lock >= 0 else 'ERROR'}")