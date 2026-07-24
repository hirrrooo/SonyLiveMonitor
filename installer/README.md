# Instalador de un clic

Aplicacion de escritorio que instala el **Smart Remote Control parcheado** en la
camara sin que el usuario tenga que usar la linea de comandos ni PMCA-RE a mano.

Sustituye a la parte manual de la
[guia](../docs/a6000-live-monitor-guide.md): conectar la camara, pulsar
**Instalar**, listo.

> Este README es la documentacion **tecnica** (como se compila y como esta
> hecho). Para usarlo, la guia es
> **[docs/installer-guide.md](../docs/installer-guide.md)**.

## Que hace

1. Detecta la camara Sony conectada por USB y muestra el modelo.
2. Instala el APK parcheado (que viaja **dentro** del ejecutable, sin internet).
3. Permite **volver atras**: reinstala el Smart Remote original de Sony, que
   tambien va incluido.
4. Opcionalmente, hace una copia del Smart Remote de tu camara por ADB.

El APK del movil **no** lo instala: eso se hace desde el propio telefono.

## Para el usuario final

Descarga el ejecutable de tu sistema desde
[Releases](https://github.com/otonielpv/SonyLiveMonitor/releases/latest):

| Sistema | Fichero |
|---|---|
| Windows | `SonyLiveMonitor-Installer-vX.Y-windows.exe` |
| macOS | `SonyLiveMonitor-Installer-vX.Y-macos.dmg` |
| Linux | `SonyLiveMonitor-Installer-vX.Y-linux` |

Antes de abrirlo:

- En la camara: **MENU → Ajustes → Conexion USB → Almacenam. masivo**.
- Conectala con un cable USB **de datos** (no de solo carga).
- Cierra Imaging Edge, PlayMemories, Fotos, Dropbox o cualquier programa que
  pueda apropiarse de la camara.

En **Linux** hay que darle permiso de ejecucion y puede hacer falta `sudo`
(o una regla de udev) para acceder al USB:

```
chmod +x SonyLiveMonitor-Installer-*-linux
./SonyLiveMonitor-Installer-*-linux
```

En **macOS**, la primera vez: clic derecho → *Abrir* (el binario no esta firmado
con una cuenta de desarrollador de Apple).

## Ejecutar desde el codigo fuente

PMCA-RE **no se instala con pip** (su repositorio no tiene `setup.py`), asi que
hay que clonarlo dentro de `installer/`:

```
git clone --branch v0.18 https://github.com/ma1co/Sony-PMCA-RE.git installer/pmca-re
pip install -r installer/requirements.txt
python installer/installer.py
```

Alternativamente, indica donde esta con la variable `PMCA_ROOT`.

> El directorio del clon **no** puede llamarse `pmca`: colisionaria con el
> paquete `pmca` que hay dentro y Python no podria importarlo.

Opciones:

| Opcion | Que hace |
|---|---|
| *(ninguna)* | Abre la ventana grafica |
| `--console` | Modo texto (util si no hay Tkinter) |
| `--restore` | Reinstala el Smart Remote original de Sony |
| `-y` | No pide confirmacion (con `--console`) |
| `--selftest` | Comprueba que los APK y PMCA-RE estan empaquetados |

En Debian/Ubuntu, Tkinter va aparte: `sudo apt install python3-tk`.

## Compilar el ejecutable

```
pyinstaller --clean --noconfirm installer/installer.spec
```

El resultado queda en `dist/`. La CI
([`installer.yml`](../.github/workflows/installer.yml)) lo compila para los tres
sistemas y lo adjunta a la Release al publicar un tag `vX.Y`.

## Versionado: el instalador va atado a su release

Cada instalador **lleva dentro** el APK de la camara, asi que instala exactamente
la version con la que se compilo. Para publicar una app nueva se saca un
instalador nuevo: la CI compila los tres binarios sola al taguear `vX.Y`.

Es una decision deliberada, a favor de que el instalador sea autonomo (funciona
sin internet) y reproducible (el mismo binario instala siempre lo mismo).

`assets.download_apk()` implementa la via alternativa —descargar el APK de la
ultima Release— y funciona, pero **no se usa**: solo actua como respaldo si algun
dia se distribuye un instalador sin APK incrustado. Si se quisiera activar la
actualizacion automatica habria que anadir al APK un numero de version propio,
porque el `versionName` que reporta la camara es siempre `4.30` (heredado de
Sony) y no distingue entre releases del proyecto.

## Estructura

- `installer.py` — punto de entrada (GUI, consola y selftest).
- `sonyinstaller/camera.py` — capa sobre PMCA-RE: deteccion e instalacion.
- `sonyinstaller/assets.py` — localiza el APK (empaquetado o descargado).
- `sonyinstaller/backup.py` — copia opcional del APK original via ADB.
- `sonyinstaller/gui.py` — ventana Tkinter.

## Volver atras

El instalador lleva dentro el **Smart Remote Control original de Sony**
(`com.sony.imaging.app.srctrl` v4.30, extraido de una a6000 sin parchear), asi
que deshacer la instalacion es pulsar **Restaurar original**. No hace falta
internet ni credenciales de la cuenta Sony.

Detalle importante: el APK parcheado usa otro nombre de paquete
(`mod.sony.imaging.app.srctrl`), asi que **las dos aplicaciones conviven** en la
camara. Restaurar no obliga a desinstalar nada: apareceran ambas en el menu
*Applications* y eliges cual abrir.

### La copia por ADB (opcional)

La casilla **Copia por ADB** guarda el APK de *tu* camara en tu disco. Ya no es
imprescindible —el original va incluido—, pero sigue ahi por si tu camara tiene
una version distinta a la 4.30 y quieres conservarla exactamente.

Requiere un paso manual que no se puede automatizar: activar ADB desde
*Applications → OpenMemories: Tweak → Developer*. A partir de ahi el instalador
descubre la IP de la camara, conecta y descarga el APK.

---

Usa [PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) (MIT, ma1co), que es quien
hace el trabajo real de hablar con la camara.
