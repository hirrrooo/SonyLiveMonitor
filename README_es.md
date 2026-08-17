# SonyLiveMonitor

Monitor en vivo de baja latencia para Sony a6000 (y otras camaras con la
Sony Camera Remote API), pensado como alternativa ligera a Imaging Edge.

*[Read this in English](README.md)*

## Instalacion rapida

Descarga el instalador de tu sistema desde la
[pagina de Releases](https://github.com/otonielpv/SonyLiveMonitor/releases/latest),
conecta la camara por USB y pulsa un boton. Sin linea de comandos ni Python.

| Sistema | Fichero |
|---|---|
| Windows | `SonyLiveMonitor-Installer-vX.Y-windows.exe` |
| macOS | `SonyLiveMonitor-Installer-vX.Y-macos.dmg` |
| Linux | `SonyLiveMonitor-Installer-vX.Y-linux` |

Guia: **[docs/installer-guide.md](docs/installer-guide.md)**. El metodo manual,
paso a paso, sigue en [docs/a6000-live-monitor-guide.md](docs/a6000-live-monitor-guide.md).

Componentes:

- **App Android nativa** (`android/`) — el monitor definitivo para el movil.
  Validada en una a6000 real: ~25 fps con ~5 ms de edad de frame.
- **App iOS** (`ios/`, SwiftUI) — port completo de la app Android para iPhone.
- **Prototipo de escritorio en Python** (raiz) — util para diagnostico y
  desarrollo desde el PC.
- **Instalador de un clic** (`installer/`) — aplicacion de escritorio para
  Windows, macOS y Linux que detecta la camara por USB e instala el Smart
  Remote parcheado sin tocar la linea de comandos. Guia de uso:
  [docs/installer-guide.md](docs/installer-guide.md); detalles tecnicos en
  [installer/README.md](installer/README.md).

## App Android ("Sony Live Monitor")

- Liveview a pantalla completa con HUD (fps, edad del frame, drops).
- Cuadriculas configurables: tercios / tercios+diagonales / cruz (persistente).
- Medidor de exposicion en tiempo real calculado del liveview: histograma de
  luminancia, desviacion EV respecto al gris medio y % de recorte
  (la API de Sony no expone el fotometro interno de la camara).
- Controles de camara: ISO, velocidad, apertura, compensacion EV y disparo
  (los valores disponibles se consultan a la camara segun el modo del dial).
- Enfoque tactil tocando la imagen (setTouchAFPosition).
- Focus peaking calculado en el movil, con color y sensibilidad configurables
  (tambien funciona con objetivos manuales sin comunicacion electronica).
- Vista espejo horizontal para grabarse mirando el monitor; solo transforma la
  previsualizacion y mantiene correcto el enfoque tactil.
- Panel escalable por pestanas (`Camera`, `View` y `App`) que evita acumular
  todos los controles en una unica rejilla, mantiene estable el tamano del
  liveview y usa tarjetas modernas con estados activos claramente visibles.
- Con Smart Remote Control parcheado en la a6000, galeria completa de la
  tarjeta mediante `avContent`, descarga separada de JPEG y RAW/ARW y borrado
  multiple con confirmacion en las camaras compatibles.
- Reconexion automatica y re-vinculacion a la WiFi activa si cambia de red.

La vista `Camera card` incluye las fotos tomadas tanto desde la app como con el
obturador fisico y evita duplicarlas automaticamente en el almacenamiento del
movil. La descarga de JPEG/ARW es siempre una accion explicita del usuario.

La opcion `Location` de la galeria permite geolocalizar tanto JPEG como Sony
ARW a resolucion completa. Hay que activarla antes de disparar: la app conserva
una pista GPS local de 24 horas y, mientras esta conectada, detecta el disparo
fisico o desde la app para congelar la posicion de ese instante. Cada descarga
se empareja despues con su hora de captura.
Solo se modifican los metadatos de la copia descargada; la imagen no se escala
ni se recomprime y el archivo de la tarjeta permanece intacto. Si no existe una
ubicacion cercana, la descarga se guarda sin modificar y se muestra un aviso.

Compilar e instalar (con el SDK de Android y un movil con depuracion USB):

```
cd android
gradle :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### Firma de las releases Android

Los APK adjuntos a tags `v*` se firman con una clave estable para que Android
permita actualizar la aplicación. Configura estos secretos en GitHub Actions:

- `ANDROID_KEYSTORE_BASE64`: contenido del keystore codificado en Base64.
- `ANDROID_KEYSTORE_PASSWORD`: contraseña del keystore.
- `ANDROID_KEY_ALIAS`: alias de la clave.
- `ANDROID_KEY_PASSWORD`: contraseña de la clave.

La clave debe conservarse: si se pierde o cambia, Android exigirá desinstalar la
versión anterior antes de instalar una nueva. Los APK antiguos publicados como
`debug` usan otra firma y también requieren una única desinstalación antes de
instalar la primera release firmada de forma estable.

Uso: camara en "Ctrl. con smartphone", movil conectado a la WiFi
`DIRECT-xxxx:ILCE-6000`, abrir la app. Se reconecta sola.

## App iOS

Port 1:1 de la app Android en SwiftUI (`ios/SonyLiveMonitor.xcodeproj`):
mismo lector de liveview anti-lag (socket crudo con `TCP_NODELAY`, solo se
conserva el frame mas reciente), mismos controles (ISO, velocidad, apertura,
enfoque, flash, temporizador, EV, WB, modo foto/video), zoom motorizado,
enfoque tactil, cuadriculas, HUD, medidor de exposicion, disparador
flotante arrastrable, vista espejo, panel por pestanas, focus peaking y la misma
galeria `Camera card` (avContent): miniaturas
paginadas, visor con zoom y paso de fotos deslizando, seleccion multiple y
descarga de JPEG/RAW con dialogo de progreso que bloquea la pantalla.

Diferencias respecto a Android:

- Hay que conectarse a la red `DIRECT-xxxx` de la camara desde Ajustes > WiFi
  antes de usar la app. El boton "WiFi" muestra las instrucciones.
- La primera vez iOS pide permiso de "red local" — hay que aceptarlo o la
  camara no sera alcanzable.
- Las descargas de la galeria se guardan en la app Archivos
  (`En mi iPhone > Sony Live Monitor`) o en la carpeta que se elija con el
  boton "Folder"; en Android van a `Download/SonyLiveMonitor`.

Compilar e instalar en un iPhone:

1. Abrir `ios/SonyLiveMonitor.xcodeproj` en Xcode.
2. En el target, ajustar el Team de firma (Signing & Capabilities) a tu
   Apple ID personal.
3. Seleccionar el iPhone como destino y Run. Con cuenta gratuita, la
   primera vez hay que confiar en el perfil en el iPhone
   (Ajustes > General > Gestion de dispositivos).

## Prototipo de escritorio (Python)

## Como funciona

La camara, en modo **Ctrl. con smartphone** (Smart Remote Control), crea un
punto de acceso WiFi y expone una API JSON-RPC. Esta app:

1. Descubre el endpoint por SSDP (o usa `http://192.168.122.1:8080/sony/camera`).
2. Llama a `startRecMode` + `startLiveview` para obtener la URL del stream.
3. Lee el stream de frames JPEG con un socket crudo (`TCP_NODELAY`) en un
   hilo dedicado que **solo conserva el frame mas reciente** — los frames
   atrasados se descartan en vez de encolarse, evitando el lag acumulado.
4. Renderiza con OpenCV mostrando FPS, edad del frame y frames descartados.

## Uso

```
pip install -r requirements.txt

# 1. En la camara: MENU > Aplicacion > Ctrl. con smartphone
# 2. Conecta el PC al WiFi que crea la camara (DIRECT-xxxx:ILCE-6000)
# 3. Ejecuta:
python monitor.py
```

Opciones utiles:

| Opcion | Descripcion |
|---|---|
| `--endpoint URL` | Salta el descubrimiento SSDP (arranque mas rapido) |
| `--size L` | Pide un liveview mas grande si la camara lo soporta |
| `--scale 2` | Factor de escala de la ventana (default 2x) |
| `--no-hud` | Oculta el overlay de FPS/latencia |

Salir: tecla `q` o `ESC`.

## Estructura

- `sony_camera.py` — descubrimiento SSDP y cliente JSON-RPC de la API.
- `liveview_stream.py` — parser del contenedor de liveview con estrategia
  "solo el ultimo frame" para minimizar latencia.
- `monitor.py` — ventana de visualizacion con HUD de rendimiento.
