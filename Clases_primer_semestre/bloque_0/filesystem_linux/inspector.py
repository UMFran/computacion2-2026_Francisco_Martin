import argparse
import os
import stat
import pwd
import grp
from pathlib import Path
from datetime import datetime
 
def crear_parser():
    parser = argparse.ArgumentParser(description="Muestra información detallada de un archivo.")
    parser.add_argument("ruta", help="Archivo, directorio o dispositivo a inspeccionar")
    return parser
 
def formato_fecha(timestamp):
    """Convierte un timestamp Unix a fecha legible."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
 
def formato_permisos(modo):
    """
    Convierte los bits de modo a formato legible rwxr-xr-x y octal 755.
    stat.filemode() hace el trabajo pesado por nosotros.
    """
    legible = stat.filemode(modo)[1:]   # sacamos el primer char (tipo) y dejamos solo permisos
    octal   = oct(stat.S_IMODE(modo))[2:]  # S_IMODE extrae solo los bits de permisos
    return legible, octal
 
def detectar_tipo(ruta, modo):
    """Detecta el tipo de archivo según los bits de modo."""
    if stat.S_ISREG(modo):
        return "archivo regular"
    elif stat.S_ISDIR(modo):
        return "directorio"
    elif stat.S_ISLNK(modo):
        destino = os.readlink(ruta)
        return f"enlace simbólico -> {destino}"
    elif stat.S_ISCHR(modo):
        return "dispositivo de caracteres"
    elif stat.S_ISBLK(modo):
        return "dispositivo de bloques"
    elif stat.S_ISFIFO(modo):
        return "pipe (FIFO)"
    elif stat.S_ISSOCK(modo):
        return "socket"
    else:
        return "tipo desconocido"
 
def formato_tamano(bytes):
    """Muestra el tamaño en bytes y en KB si corresponde."""
    if bytes >= 1024:
        return f"{bytes} bytes ({bytes/1024:.2f} KB)"
    return f"{bytes} bytes"
 
def inspeccionar(ruta):
    path = Path(ruta)
 
    if not path.exists() and not path.is_symlink():
        print(f"Error: no existe '{ruta}'")
        return
 
    # lstat() no sigue symlinks (nos da info del link en sí, no del destino)
    info = path.lstat()
    modo = info.st_mode
 
    # Nombre de usuario y grupo desde uid/gid
    try:
        usuario = pwd.getpwuid(info.st_uid).pw_name
    except KeyError:
        usuario = str(info.st_uid)
 
    try:
        grupo = grp.getgrgid(info.st_gid).gr_name
    except KeyError:
        grupo = str(info.st_gid)
 
    permisos_legible, permisos_octal = formato_permisos(modo)
    tipo = detectar_tipo(ruta, modo)
 
    print(f"Archivo: {ruta}")
    print(f"Tipo: {tipo}")
    print(f"Tamaño: {formato_tamano(info.st_size)}")
    print(f"Permisos: {permisos_legible} ({permisos_octal})")
    print(f"Propietario: {usuario} (uid: {info.st_uid})")
    print(f"Grupo: {grupo} (gid: {info.st_gid})")
    print(f"Inodo: {info.st_ino}")
    print(f"Enlaces duros: {info.st_nlink}")
    print(f"Última modificación: {formato_fecha(info.st_mtime)}")
    print(f"Último acceso: {formato_fecha(info.st_atime)}")
    print(f"Último cambio de metadatos: {formato_fecha(info.st_ctime)}")
 
    # Para directorios, contar elementos dentro
    if stat.S_ISDIR(modo):
        try:
            elementos = len(list(path.iterdir()))
            print(f"Contenido: {elementos} elementos")
        except PermissionError:
            print("Contenido: sin permiso para listar")
 
def main():
    parser = crear_parser()
    args = parser.parse_args()
    inspeccionar(args.ruta)
 
if __name__ == "__main__":
    main()