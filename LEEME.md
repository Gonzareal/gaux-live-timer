# Gaux Live Timer

Widget flotante que aparece al abrir tu DAW (Ableton Live, FL Studio, Logic Pro, Pro Tools, Cubase, Studio One, Bitwig, REAPER, Reason, GarageBand y más) y cuenta solo el tiempo que trabajas de verdad, proyecto por proyecto.

## Cómo cuenta
- Cuenta cuando Live (o una ventana de plugin de Live) está al frente y has tocado teclado o mouse dentro del límite de inactividad (5 min por defecto).
- Se pausa si cambias a otra app, si minimizas Live, o si te quedas quieto más del límite.
- Minimizar el widget no cambia nada: sigue contando con la misma regla.
- El widget solo se ve cuando Live está al frente. Si pasas a otra app (navegador, Finder, etc.) se oculta solo y vuelve a aparecer al regresar a Live.

## Cualquier DAW
El timer reconoce Ableton Live, FL Studio, Logic Pro, Pro Tools, Cubase, Nuendo, Studio One, Bitwig Studio, REAPER, Reason, GarageBand, Cakewalk, Ardour, Renoise y Digital Performer. En ⚙ → **DAWs que reconoce** eliges cuáles vigilar, y en **Otras apps** puedes agregar cualquier otra por su nombre (separadas por comas). Todo lo demás (contar solo con el DAW al frente, pausar sin actividad, Top Live) funciona igual con cualquiera.

## Proyectos: cuánto tiempo llevas en cada uno
Cada minuto que cuenta el timer se suma al **proyecto activo**, y queda guardado: total, hoy, semana, mes, número de sesiones, última vez y DAW.
- **Automático:** el timer lee el nombre del proyecto en el título de la ventana del DAW (por ejemplo "Confession Remix" en Live, "MiTema.flp" en FL Studio) y cambia solo cuando abres otro. En Mac, para leer ese título hay que activar **Terminal** en Ajustes del Sistema → Privacidad y seguridad → **Grabación de pantalla y audio del sistema** (el timer no graba nada: macOS pide ese permiso para leer títulos de ventanas). En Windows funciona sin permisos.
- **Manual:** elige el proyecto con doble clic → **Proyecto**, o haciendo clic en la línea del proyecto dentro del timer. Ahí también creas uno nuevo. Si eliges a mano, la detección automática se apaga (la vuelves a encender en el mismo menú). Los proyectos sin nombre ("Sin título") usan el que elijas a mano; si no eliges ninguno, el tiempo va a **Sin asignar**.
- **Ver proyectos…** (doble clic → Ver proyectos, o ⚙ → Proyectos) abre la tabla con todos tus proyectos. Clic en una columna para ordenar; **Usar**, **Renombrar** (si el nombre ya existe, se unen sus horas) y **Eliminar**. **Exportar CSV** guarda el historial en el Escritorio para abrirlo en Numbers, Excel o Google Sheets.
- El proyecto activo y su total se ven en la vista completa, y en la franja de Top Live junto al estado.
- El tiempo por proyecto se empieza a registrar desde esta versión; las horas anteriores siguen en Hoy/Semana/Mes.

## Modo Personal
Un estilo para que el timer sea tuyo: en ⚙ → Estilo → **Personal**.
- **Tu nombre** como título del timer.
- **Frase de inicio:** aparece cada vez que abres tu DAW, como el "LET'S GAUUUUX" del Gaux Mode, pero con lo que tú quieras escribir.
- **Frase de cierre:** el titular de la tarjeta con el resumen al cerrar el DAW (sesión, hoy, proyecto y semana).
- **Color** (ocho rápidos, un código #RRGGBB o "Más…" para elegir cualquiera), **forma** redondeada o angular y **efectos** (rayos, glitch y barrido) encendidos o apagados. El analizador toma tu color.
- A diferencia del Gaux Mode, aquí sí puedes elegir las letras del título y del reloj.

## Menú de opciones
**Doble clic en cualquier parte del timer** (o ctrl+clic) abre el menú: pausar/reanudar, tomar break, reiniciar sesión, **proyecto**, **ver proyectos**, ajustes, estilo, modo, vista, analizador, Top Live y **Cerrar Gaux Live Timer**.

## Vistas
- **Completa:** reloj, metas y línea del modo autónomo.
- **Compacta:** solo título y reloj.
- **Minimizada:** una cápsula pequeña con el reloj, pensada para la barra de Live. Botón **–** para minimizar; **□** para volver.
- **Orientación:** horizontal o vertical (Ajustes → Orientación, o ctrl+clic → Vista). En vertical el reloj se apila en horas, minutos y segundos.
- **Tamaño ajustable:** arrastra el borde derecho, el inferior o la esquina (aparece un asa al pasar el mouse), o usa ⚙ → Apariencia → **Tamaño del timer** (− / +, se ve al instante). Vista completa/compacta: 75 % a 200 %; minimizada: **60 % a 220 %**, así la cápsula cabe en la barra de título de Live sin tapar botones. Ningún texto baja de 8 pt. Para volver al tamaño de fábrica: botón **Original** o doble clic → Vista → Tamaño original.
- Cada vista y orientación recuerda su propia posición y su propio tamaño.

## Top Live Performance
Modo para producir viendo tu tiempo y tus medidores sin tapar nada de Live:
- Acopla el timer (a la izquierda) y el analizador (a lo ancho) en una franja arriba de la ventana de Live.
- **Baja la ventana de Live justo debajo de la franja**, así no se esconde ningún botón, ni el navegador de la izquierda, ni las pistas de la derecha.
- Al desactivarlo, Live vuelve a su tamaño y el timer y el analizador a donde estaban.
- Si cierras y vuelves a abrir Live con el modo activo, le vuelve a hacer espacio solo.
- **Se adapta a cualquier pantalla:** la franja se pega arriba, justo bajo la barra de menú de la pantalla donde está Live, y toma el ancho de la ventana de Live. Si cambias la resolución (Ajustes del Sistema → Pantallas → "Más espacio", etc.), conectas un monitor o mueves Live a otra pantalla, en uno o dos segundos todo se reacomoda solo. Si la ventana de Live vuelve a tapar la franja (por ejemplo, al maximizarla), se baja sola.

Se activa con ctrl+clic en el timer → **Top Live Performance**, o en ⚙ → Top Live Performance.

**Tamaño de la franja:** de 100 % a 50 % (ctrl+clic → Tamaño de la franja Top Live, o en ⚙). Al achicarla todo se reacomoda para seguir siendo legible: por debajo de ~100 px se ocultan los títulos de los módulos, el timer pasa a una fila y el loudness a una línea. Live se ajusta al instante.

**Pantalla completa (Mac):** al activar el modo, el timer saca a Live de pantalla completa y lo deja ocupando toda la pantalla bajo la franja. Si después pones Live en pantalla completa, el timer y un analizador compacto (onda, espectro y loudness) pasan a la franja negra de arriba, a los lados de la cámara, sin tapar nada de Live. Al salir de pantalla completa vuelven a la franja normal. En pantallas sin cámara (monitor externo) la franja queda encima de Live mientras esté en pantalla completa.

**Barra de menú y botones de ventana:** lleva el mouse al borde superior de la pantalla y la franja se aparta para que macOS muestre la barra de menú y los botones de la ventana (por ejemplo, para salir de pantalla completa). Mientras un menú de Live (Archivo, Edición…) siga abierto, la franja no vuelve; regresa sola cuando eliges una opción o cierras el menú y bajas el mouse.

**En Mac** la primera vez hay que dar permiso para mover la ventana de Live: Ajustes del Sistema → Privacidad y seguridad → **Accesibilidad** → activa **Terminal** (y si aparece "Terminal quiere controlar System Events", **Permitir**).
**En Windows** no hace falta ningún permiso.

El timer siempre queda por encima del analizador, también fuera de este modo.

**Plugins siempre libres:** el timer y el analizador quedan por encima de la ventana principal de Live, pero **siempre por debajo de las ventanas de plugins** (Serum, Drum Monkey, etc.). Así puedes mover y cerrar cualquier plugin aunque se abra encima del timer o de la franja. Además, hacer clic en el timer no le quita el foco a Live (no se esconden los plugins ni dejan de funcionar los atajos de teclado). En Windows pasa lo mismo: el timer queda "pegado" a la ventana del DAW sin tapar sus plugins.

**Diálogos desde el menú:** en Top Live, si eliges en la barra de menú algo que abre un diálogo (Archivo → Exportar audio/video…), la franja sigue apartada hasta que lo cierras.

**Cero interferencia con Live:** mientras produces, el timer nunca le consulta nada a Live; solo pregunta al sistema qué app está al frente. Así no afecta clics, doble clics ni arrastres de clips y samples. Solo se oculta cuando cambias de verdad a otra app (lo confirma dos veces seguidas), y la franja de Top Live no se aparta mientras tengas el botón del mouse presionado.

## Rendimiento
Pensado para dejarlo encendido todo el día sin cargar el Mac:
- ⚙ → Apariencia → **Fluidez**: *120 fps* (todo a 120), *Equilibrado* (predeterminado: onda y medidores a 120 mientras suena; timer, espectro y stereo a 60) o *60 fps* (todo a 60).
- **Mientras suena** va a la fluidez elegida. **Al parar**, la onda termina de pasar con fluidez y recién cuando todo quedó quieto el analizador baja a 15 fps (no se nota).
- Mover la ventana de Live o revisar sus menús se hace en segundo plano: el timer nunca se congela esperando a macOS.
- **Con otra app al frente** (o Live cerrado) el timer y el analizador dejan de dibujar por completo.
- Las animaciones van según el tiempo real: se ven igual de rápidas a 60 que a 120, solo más suaves.
- El timer ya no lanza procesos cada pocos segundos para saber si Live está abierto: se lo pregunta directo a macOS.
- Para gastar todavía menos: *60 fps* y ⚙ → Animaciones en OFF.
- ctrl+clic en el timer muestra arriba los fps reales del timer y del analizador.

## Estilos
Gaux Mode, Noche morada, Cristal (semitransparente), Neón, Atardecer y Medianoche. Se cambian con ctrl+clic → Estilo, o en Ajustes (⚙), donde también eliges la opacidad, las animaciones y las letras del título y del reloj.

### Gaux Mode — Let's Gauuuux
Modo único. Solo para los más audaces.
Tipografía fija: este modo no se personaliza, se vive.

- **Ritual de sesión:** cada vez que abres Live aparece "LET'S GAUUUUX"; al cerrarlo, una tarjeta "GG" con tu tiempo de la sesión y del día (y "GOAL CRUSHED" si cumpliste la meta). Se va sola en unos segundos, o con un clic.
- **Vocabulario propio:** LOCKED IN (en sesión), HOLD (pausa), RECHARGE (break), STANDBY (esperando a Live), GOAL CRUSHED (meta cumplida).

## Ajustes (⚙)
Una ventana con secciones a la izquierda; cada una explica en una línea qué hace:
- **Metas:** una tarjeta por meta (Hoy, Semana, Mes). Interruptor para activarla, toca el nombre para cambiarlo, − / + para ajustar las horas (mantén presionado para ir rápido) o elige un atajo (2 h, 4 h, 20 h…). Cada tarjeta muestra cuánto llevas y cuánto te falta. Abajo: cuántos minutos sin tocar nada pausan el contador.
- **Descansos:** elige entre *Avisarme cuándo descansar* o *Solo contar mi tiempo*. Si eliges avisos, pones cada cuánto descansar, cuánto dura el descanso y a partir de cuántas horas al día te avisa (o *Nunca*).
- **Apariencia:** estilo, tamaño del timer, vista, orientación, opacidad, animaciones, fluidez y letras.
- **Top Live**, **DAW y proyectos** y **Analizador** (con el Diagnóstico de audio a un clic).

## Metas
Diaria, semanal y mensual (se ajustan en ⚙ → Metas). Al cumplir una, la barra se vuelve dorada con una pequeña celebración.

## Pausa y break
- **Botón ❚❚ / ▶** (arriba, junto al –; también en la vista minimizada): pausa y reanuda el contador a mano.
- **Tomar break:** en modo autónomo aparece cuando se acerca o llega la hora del break. Muestra la cuenta regresiva del descanso.
- **Volver / Reanudar:** termina el break. Si descansaste el tiempo completo, la racha vuelve a cero.
- También están en el menú de ctrl+clic.

## Modo autónomo
Vigila tu racha de trabajo continuo, solo con indicadores dentro del timer (sin notificaciones):
- **Morado:** todo bien, muestra la racha y cuánto falta para el break.
- **Ámbar:** faltan pocos minutos.
- **Rojo pulsante:** toca break para descansar y estirar.
- Si te alejas el tiempo del break (5 min por defecto), la racha vuelve a cero sola.
- También se pone en rojo si pasas las horas máximas del día (8 h por defecto).

Todo esto se ajusta en ⚙. En modo **Normal** no hay indicadores de break.

## Analizador de audio (opcional)
Franja aparte, solo de visualización, a 120 fps (la onda avanza a paso fijo de 1 px por cuadro; 2 px a 60 fps), con cuatro módulos:
- **Waveform:** forma de onda con color por frecuencia. Dos modos de color: **Tema** (sigue el estilo: rosa/morado/cian en Noche morada, rojo/gris/blanco en Gaux Mode) y **RGB estándar** (rojo = graves, verde = medios, azul = agudos). Se elige con ctrl+clic en el panel → Color de la onda, o en ⚙ → Analizador.
- **Spectrum + Spectrogram:** curva FFT con escalas como SPAN (20, 30, 40… 1K… 20K y dB cada 6 a la derecha; en tamaños pequeños solo las principales), suavizado de 1/12 de octava, inclinación 4.5 dB/oct, y espectrograma de colores.
- **Stereo:** vectorscopio (vertical = mono, ancho = estéreo) y correlación de fase (+1 mono, 0 ancho, negativo = problemas de fase).
- **Loudness:** LUFS short-term (grande), momentary, integrado y true peak máximo, según ITU-R BS.1770 / EBU R128; medidores L/R/M e historial de 60 s con referencia de -14 LUFS.

Uso: ctrl+clic en el timer → **Analizador de audio**, o en ⚙ → Analizador. Arrástralo para moverlo, la esquina inferior derecha lo redimensiona, ctrl+clic encima elige módulos y muestra la entrada de audio activa, doble clic reinicia el integrado y el true peak. Se oculta solo cuando sales de Live, igual que el timer.

### Instalación (una vez)
```
python3 -m pip install numpy sounddevice
```

### Conectar el audio de Live — Mac (BlackHole)
1. Instala **BlackHole 2ch** (gratis): https://existential.audio/blackhole/ (o `brew install blackhole-2ch`).
2. Abre **Configuración de Audio MIDI** (Aplicaciones → Utilidades).
3. Botón **+** abajo a la izquierda → **Crear dispositivo de salida múltiple**.
4. Marca tu interfaz de audio (o los parlantes/audífonos) **y** BlackHole 2ch. Deja tu interfaz como **Dispositivo principal** y activa **Corrección de deriva** solo en BlackHole.
5. En Live → Preferencias → Audio: **Dispositivo de salida** = el dispositivo de salida múltiple. La entrada se queda como siempre.
6. En el timer: ⚙ → Analizador → Entrada de audio = **BlackHole 2ch** (o "Automático").
7. La primera vez, macOS pedirá permiso de micrófono para la Terminal: dale **Permitir** (BlackHole cuenta como entrada).

Sigues escuchando por tu interfaz igual que siempre; BlackHole solo recibe una copia para el analizador.

### Si el analizador no se mueve (por ejemplo, después de actualizar macOS)
El analizador ahora te dice qué pasa:
- **"Esperando audio de BlackHole 2ch…"**: la entrada está abierta pero llega silencio total. Dale play en Live. Si suena y sigue quieto, casi siempre es una de estas dos cosas:
  1. **Live → Ajustes → Audio → Dispositivo de salida** tiene que ser el *Dispositivo de salida múltiple* (macOS a veces lo cambia al actualizarse).
  2. En **Configuración de Audio MIDI**, el dispositivo de salida múltiple tiene que tener marcados tu salida **y BlackHole 2ch**.
- **"macOS está bloqueando el audio"**: Ajustes del Sistema → Privacidad y seguridad → **Micrófono** → activa **Terminal**. Las actualizaciones de macOS a veces quitan este permiso.
- **ctrl+clic en el analizador → Diagnóstico de audio** muestra la entrada, el permiso y el nivel real que llega, con botones para abrir los ajustes y reconectar.
- Si la entrada se cae (el Mac durmió, reinstalaste BlackHole, cambiaste de interfaz), se **reconecta sola**. También puedes forzarlo: ctrl+clic → **Reconectar audio**.
- Prueba sin abrir el timer, en la Terminal: `cd ~/ft_userdata && python3 gaux_analizador.py --test` (dale play en Live mientras escucha 5 segundos; al final dice si el audio llega o qué revisar).

### Conectar el audio de Live — Windows
- **VB-Cable** (gratis, https://vb-audio.com/Cable/): pon "CABLE Input" como salida en Live y escucha el cable desde Sonido → Grabación → CABLE Output → Escuchar este dispositivo → tu salida. En el timer elige **CABLE Output**.
- Si usas la tarjeta de sonido integrada, también sirve **Mezcla estéreo** (Stereo Mix), aunque capta todo el sonido del PC.

## Instalar (Mac y Windows)
Los instaladores se arman solos en GitHub cada vez que cambia el código (ver README.md):
- **Mac:** `GauxLiveTimer_Mac.zip` → `Gaux Live Timer.pkg` instala la app en Aplicaciones y el plugin **Gaux Link** (VST3 y AU). Apple Silicon (M1 o más nuevo), macOS 12+.
- **Windows:** `GauxLiveTimer_Windows.zip` → instalador con la app y Gaux Link (VST3). Windows 10/11 de 64 bits.

Como no están firmados con cuentas pagas, la primera vez macOS pide **Ajustes del Sistema → Privacidad y seguridad → Abrir igualmente**, y Windows muestra "Windows protegió su PC" → **Más información → Ejecutar de todas formas**. Cada zip trae un "ANTES DE INSTALAR" con los pasos.

### Usar la app
- Aparece sola cuando tu DAW está al frente. No tiene ícono en el Dock.
- Para ver los Ajustes: doble clic sobre el timer, o abre la app otra vez (Aplicaciones / menú Inicio).
- ⚙ → **General**: abrir al iniciar sesión, carpeta de datos, versión y **Salir**.
- Los permisos de macOS son para **Gaux Live Timer**. Después de instalar una versión nueva, macOS puede volver a pedirlos.
- Si algo falla, los errores quedan en `~/.live_timer/registro.txt`.

## Gaux Link (audio para el analizador, sin BlackHole)
Plugin que se instala junto con la app. Ponlo **al final del Master** de tu DAW:
- Deja pasar el audio sin tocarlo y le manda una copia al analizador por la red interna del computador.
- Con el analizador en **Automático**, el timer lo usa solo apenas recibe audio (y vuelve a BlackHole si quitas el plugin).
- No necesita BlackHole, VB-Cable, dispositivo de salida múltiple ni permiso de micrófono.
- Su ventana dice si está **Enviando**, **En espera** (otra pista ya envía: déjalo solo en el Master) o si falta abrir la app.
- ctrl+clic en el analizador → **Diagnóstico de audio** muestra el DAW, la pista y la frecuencia que llegan.

## Armar los instaladores
- **Automático (recomendado):** cada cambio subido a GitHub arma y prueba los instaladores de Mac y Windows (pestaña *Actions*). Los últimos quedan para descargar directo; ver README.md.
- **Nueva versión:** cambia `VERSION = "1.0"` en `live_timer.py`. Para publicar una versión con número (Release), crea una etiqueta `v1.0`.
- **En tu Mac (opcional):** `bash build_mac.sh` (necesita cmake y Xcode para el plugin).

## Ejecutar (macOS)
```
cd ~/ft_userdata
python3 live_timer.py --demo             (vista previa sin Live)
python3 live_timer.py                    (modo real)
python3 live_timer.py --instalar-inicio  (arrancar con el Mac)
```
La demo guarda en un archivo aparte, así que no ensucia tu historial real.

Si ya hay un timer abierto, volver a ejecutar `python3 live_timer.py` lo cierra y abre la versión más reciente en su lugar.

## Ejecutar (Windows)
```
pip install psutil
python live_timer.py --demo
python live_timer.py --instalar-inicio
```

## Datos
`~/.live_timer/datos.json`: segundos por día y una lista de sesiones. `~/.live_timer/config.json`: tus ajustes.

## Limitaciones conocidas
- El analizador muestra lo que llega a la entrada elegida: con BlackHole es exactamente la salida de Live.
- En Mac, si Live está en pantalla completa (su propio Space), el widget no se ve encima. Usa Live en ventana maximizada.
