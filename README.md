# OptiSolver Desktop

Aplicación de escritorio para resolver problemas de **programación lineal** con el **Método Simplex Primal** y el **Método Simplex Dual**, mostrando el procedimiento paso a paso (tabla inicial y cada iteración).

Desarrollada en Python con Tkinter. No requiere librerías externas para ejecutarse.

## Características

- Maximizar o minimizar, con hasta 10 variables y 10 restricciones.
- Restricciones `≤`, `≥` y `=`.
- Selección del algoritmo: Simplex Primal o Simplex Dual.
- Matriz de entrada dinámica (se ajusta al número de variables y restricciones).
- Tabla de cada iteración con el pivote resaltado, la variable que entra y la que sale, y los cocientes de la prueba mínima.
- Resumen final: variables básicas, vector óptimo x* y valor óptimo Z*.
- Aritmética exacta con fracciones (sin errores de redondeo).
- Alertas visuales para solución **no acotada**, problema **infactible** y datos o método no válidos.
- Tema oscuro diseñado para no cansar la vista.

## Requisitos

- Python 3.9 o superior (probado en 3.12).
- Tkinter (incluido con Python en Windows y macOS; en Linux: `sudo apt install python3-tk`).

## Ejecución desde el código fuente

```bash
git clone <https://github.com/xerozasshuken-svg/OptiSolver-Desktop.git>
cd OptiSolver-Desktop
python main.py
```

En Windows, si `python` no funciona, use `py main.py`.

## Ejecutable

Para generar el ejecutable (`.exe` en Windows) se usa PyInstaller:

**Windows:** doble clic en `build.bat`, o desde la terminal:

```bat
build.bat
```

**Linux / macOS:**

```bash
chmod +x build.sh
./build.sh
```

El archivo resultante queda en la carpeta `dist/` (`dist/OptiSolver.exe` en Windows). El ejecutable generado se puede copiar y abrir en otro equipo sin tener Python instalado.

El repositorio incluye además un flujo de GitHub Actions (`.github/workflows/build.yml`) que genera el `.exe` de Windows automáticamente desde la pestaña *Actions*.

## Pruebas

Las pruebas verifican el motor Simplex y lo comparan con SciPy en 200 problemas aleatorios:

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

## Estructura del proyecto

```
OptiSolver-Desktop/
├── main.py              # Punto de entrada
├── gui.py               # Interfaz gráfica (Tkinter + ttk)
├── simplex.py           # Lógica del Simplex Primal y Dual (sin interfaz)
├── tests/
│   └── test_simplex.py  # Pruebas del motor
├── build.bat            # Genera el ejecutable en Windows
├── build.sh             # Genera el ejecutable en Linux / macOS
├── requirements-dev.txt # Dependencias de pruebas y empaquetado
├── GUIA_DE_USO.txt      # Manual de usuario y casos de prueba
└── README.md
```

## Notas sobre el alcance

- **Simplex Primal:** requiere lados derechos ≥ 0 (solución inicial factible). Se agregan variables de holgura automáticamente.
- **Simplex Dual:** requiere una solución inicial superóptima, es decir, todos los valores del renglón Z ≥ 0 (caso típico: minimizar con costos ≥ 0 y restricciones `≥`).
- No se implementan variables artificiales (Gran M / Dos Fases). Si el problema no cumple las condiciones del método elegido, la aplicación lo indica con un mensaje.
- Las restricciones `=` se convierten internamente en dos desigualdades (`≤` y `≥`).
- Regla de desempate: en caso de empate en el cociente mínimo se elige la variable con menor índice.

Consulte `GUIA_DE_USO.txt` para el manual completo y los casos de prueba con resultados esperados.
