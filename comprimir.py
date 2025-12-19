import os
import zipfile

os.chdir("/Users/Alamb/Documents/")

with zipfile.ZipFile("comprimido.zip", "w") as fzip:
    for carpeta, subcarpetas, archivos in os.walk("contabilidadProject"):
        for archivo in archivos:
            ruta_completa = os.path.join(carpeta, archivo)
            fzip.write(ruta_completa, os.path.relpath(ruta_completa, "contabilidadProject"))