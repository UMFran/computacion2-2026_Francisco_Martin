import argparse
import json
import sys
from pathlib import Path

ARCHIVO = Path.home() / ".tareas.json"  # ~/.tareas.json

# ── Persistencia ────────────────────────────────────────────────────────────

def cargar():
    if not ARCHIVO.exists():
        return []
    with open(ARCHIVO) as f:
        return json.load(f)

def guardar(tareas):
    with open(ARCHIVO, "w") as f:
        json.dump(tareas, f, indent=2, ensure_ascii=False)

# ── Subcomandos ──────────────────────────────────────────────────────────────

def cmd_add(args):
    tareas = cargar()
    nuevo_id = max((t["id"] for t in tareas), default=0) + 1
    tarea = {
        "id":       nuevo_id,
        "desc":     args.descripcion,
        "priority": args.priority,
        "done":     False,
    }
    tareas.append(tarea)
    guardar(tareas)
    if args.priority:
        print(f"Tarea #{nuevo_id} agregada (prioridad: {args.priority})")
    else:
        print(f"Tarea #{nuevo_id} agregada")

def cmd_list(args):
    tareas = cargar()

    # Filtros
    if args.pending:
        tareas = [t for t in tareas if not t["done"]]
    elif args.done:
        tareas = [t for t in tareas if t["done"]]
    if args.priority:
        tareas = [t for t in tareas if t["priority"] == args.priority]

    if not tareas:
        print("No hay tareas.")
        return

    for t in tareas:
        marca    = "x" if t["done"] else " "
        prioridad = f" [{t['priority'].upper()}]" if t["priority"] == "alta" else ""
        print(f"#{t['id']} [{marca}] {t['desc']}{prioridad}")

def cmd_done(args):
    tareas = cargar()
    for t in tareas:
        if t["id"] == args.id:
            t["done"] = True
            guardar(tareas)
            print(f"Tarea #{args.id} completada")
            return
    print(f"Error: no existe la tarea #{args.id}", file=sys.stderr)
    sys.exit(1)

def cmd_remove(args):
    tareas = cargar()
    for t in tareas:
        if t["id"] == args.id:
            resp = input(f'¿Eliminar "{t["desc"]}"? [s/N] ')
            if resp.lower() == "s":
                tareas.remove(t)
                guardar(tareas)
                print(f"Tarea #{args.id} eliminada")
            else:
                print("Cancelado")
            return
    print(f"Error: no existe la tarea #{args.id}", file=sys.stderr)
    sys.exit(1)

# ── Parser ───────────────────────────────────────────────────────────────────

def crear_parser():
    parser = argparse.ArgumentParser(description="Gestor de tareas.")
    sub = parser.add_subparsers(dest="comando")  # dest guarda qué subcomando usó el usuario

    # add
    p_add = sub.add_parser("add", help="Agregar una tarea")
    p_add.add_argument("descripcion", help="Descripción de la tarea")
    p_add.add_argument("--priority", choices=["baja", "media", "alta"],
                       help="Prioridad de la tarea")

    # list
    p_list = sub.add_parser("list", help="Listar tareas")
    p_list.add_argument("--pending",  action="store_true", help="Solo pendientes")
    p_list.add_argument("--done",     action="store_true", help="Solo completadas")
    p_list.add_argument("--priority", choices=["baja", "media", "alta"],
                        help="Filtrar por prioridad")

    # done
    p_done = sub.add_parser("done", help="Marcar tarea como completada")
    p_done.add_argument("id", type=int, help="ID de la tarea")

    # remove
    p_remove = sub.add_parser("remove", help="Eliminar una tarea")
    p_remove.add_argument("id", type=int, help="ID de la tarea")

    return parser

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = crear_parser()
    args = parser.parse_args()

    # Si no se pasó ningún subcomando, mostrar ayuda
    if not args.comando:
        parser.print_help()
        sys.exit(0)

    # Despachar al subcomando correspondiente
    comandos = {
        "add":    cmd_add,
        "list":   cmd_list,
        "done":   cmd_done,
        "remove": cmd_remove,
    }
    comandos[args.comando](args)

if __name__ == "__main__":
    main()