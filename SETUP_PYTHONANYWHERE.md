# SETUP PYTHONANYWHERE - Guía Paso a Paso

## PASO 1: Subir código a GitHub

### En tu PC (Windows):

```bash
cd c:\Users\MM\expedientes-app\trading\Bot2\forward_testing_pythonanywhere

# Inicializar git
git init
git add .
git commit -m "Initial commit: Forward testing system"

# Conectar con tu repo
git remote add origin https://github.com/Marmor00/trading.git
git branch -M main
git push -u origin main
```

---

## PASO 2: Configurar PythonAnywhere

### 2.1 Abrir Bash Console

1. Ve a: https://www.pythonanywhere.com/user/Marmor00/
2. Click en **"Consoles"** tab
3. Click **"Bash"**

### 2.2 Clonar repo

```bash
# Clonar tu repo
git clone https://github.com/Marmor00/trading.git
cd trading

# Verificar archivos
ls -la
```

### 2.3 Instalar dependencias

```bash
pip3 install --user beautifulsoup4==4.12.3
pip3 install --user requests==2.31.0
```

### 2.4 Crear carpeta de datos y logs

```bash
mkdir -p data
mkdir -p logs
```

### 2.5 Configurar variables de entorno

```bash
# Crear archivo .env
nano .env
```

Pegar esto (y guardar con Ctrl+O, Enter, Ctrl+X):

```
MASSIVE_API_KEY=bDVUapvtKp6jBl7vqQdiOWCcX5kIvWmT
TELEGRAM_BOT_TOKEN=8464111172:AAFOd6oUT1ta-vcoGZJY-jEySnBw69ADosI
TELEGRAM_CHAT_ID=5542606013
```

### 2.6 Hacer script ejecutable

```bash
chmod +x run_daily.sh
```

---

## PASO 3: Test Manual

### 3.1 Ejecutar monitor

```bash
# Cargar variables
export $(cat .env | xargs)

# Ejecutar
python3 daily_monitor.py
```

**Deberías ver:**
- Scraping de OpenInsider
- Filtros aplicados
- Notificación en Telegram

### 3.2 Ver resultados

```bash
python3 view_results.py
```

**Deberías ver:**
- Portfolios inicializados ($10,000 cada uno)
- Trades activos (si hubo alguno)

---

## PASO 4: Configurar Scheduled Task

### 4.1 Ir a Tasks tab

1. En PythonAnywhere, click en **"Tasks"**
2. En **"Scheduled tasks"**, click **"Create a new scheduled task"**

### 4.2 Configurar tarea

- **Command:** `/home/Marmor00/trading/run_daily.sh`
- **Hour (UTC):** `18`
- **Minute:** `00`

### 4.3 Click "Create"

---

## PASO 5: Verificar que funciona

### 5.1 Esperar a las 6 PM UTC (o ejecutar manual)

```bash
# Ejecutar manualmente para probar
bash run_daily.sh
```

### 5.2 Ver logs

```bash
tail -n 50 logs/daily_monitor.log
```

### 5.3 Revisar Telegram

Deberías haber recibido notificaciones de:
- Nuevos trades (si hubo)
- Resumen diario

---

## TROUBLESHOOTING

### Problema: "No module named 'bs4'"

```bash
pip3 install --user beautifulsoup4
```

### Problema: "Permission denied: run_daily.sh"

```bash
chmod +x run_daily.sh
```

### Problema: "No such file or directory: .env"

```bash
nano .env
# Pegar las variables y guardar
```

### Problema: Telegram no envía mensajes

```bash
# Test manual
python3 -c "
import os
os.environ['TELEGRAM_BOT_TOKEN'] = '8464111172:AAFOd6oUT1ta-vcoGZJY-jEySnBw69ADosI'
os.environ['TELEGRAM_CHAT_ID'] = '5542606013'
import requests
url = f'https://api.telegram.org/bot{os.environ[\"TELEGRAM_BOT_TOKEN\"]}/sendMessage'
data = {'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'text': 'Test from PythonAnywhere'}
print(requests.post(url, data=data).json())
"
```

### Problema: "100 CPU seconds exceeded"

Esto significa que el script tomó más de 100 segundos.

**Soluciones:**
1. Reducir número de tickers a trackear
2. Aumentar sleep time entre API calls
3. Upgrade a Hacker plan ($5/mes)

---

## COMANDOS ÚTILES

### Ver estado de scheduled task

En PythonAnywhere web interface, ir a **Tasks** tab.

### Ver logs en tiempo real

```bash
tail -f logs/daily_monitor.log
```

### Actualizar código desde GitHub

```bash
cd /home/Marmor00/trading
git pull origin main
```

### Ver database

```bash
sqlite3 data/forward_testing.db "SELECT * FROM portfolios;"
```

---

## SIGUIENTE PASO

Una vez configurado, el sistema:

1. **Ejecuta automático** todos los días a las 6 PM UTC (1 PM México)
2. **Scrapea** OpenInsider
3. **Filtra** trades con 5 estrategias
4. **Trackea** precios con Massive API
5. **Ejecuta** paper trading (compra/venta simulada)
6. **Notifica** vía Telegram

**Tú solo:**
- Recibes notificaciones Telegram
- Cuando quieras, ejecutas `python3 view_results.py` para ver dashboard

**En 30 días:**
- Revisa win rate de cada estrategia
- Si ≥60% → Estrategia funciona ✅
- Si <50% → PIVOTEAR ❌

---

**¡Listo! Sistema 100% automático**
