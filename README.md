# Forward Testing System - Insider Trading

Sistema automático de validación de estrategias de insider trading con OpenInsider.

## Estrategias Trackeadas

1. **Score ≥80** - Multi-factor (CEO/CFO + Cluster + Valor)
2. **Score ≥85** - Threshold alto
3. **Mega Whale >$10M** - Ballenas grandes
4. **Ultra Whale >$50M** - Ballenas gigantes
5. **CEO Cluster 5+** - 5+ CEOs/CFOs comprando

## Setup en PythonAnywhere

### 1. Clonar repo

```bash
git clone https://github.com/Marmor00/trading.git
cd trading
```

### 2. Instalar dependencias

```bash
pip3 install --user -r requirements.txt
```

### 3. Configurar variables de entorno

En PythonAnywhere, ir a **Files** → crear archivo `.env`:

```bash
MASSIVE_API_KEY=bDVUapvtKp6jBl7vqQdiOWCcX5kIvWmT
TELEGRAM_BOT_TOKEN=8464111172:AAFOd6oUT1ta-vcoGZJY-jEySnBw69ADosI
TELEGRAM_CHAT_ID=5542606013
```

Luego en Bash console:

```bash
source .env
export $(cat .env | xargs)
```

### 4. Test manual

```bash
python3 daily_monitor.py
```

### 5. Configurar scheduled task

1. Ir a **Tasks** tab
2. Crear nueva **scheduled task**
3. Command: `/home/Marmor00/trading/run_daily.sh`
4. Hora: `18:00` (UTC)

## Ver Resultados

```bash
python3 view_results.py
```

## Estructura

- `daily_monitor.py` - Motor principal
- `view_results.py` - Dashboard local
- `data/forward_testing.db` - SQLite database
- `requirements.txt` - Dependencias

## Exit Rules

- Stop loss: -10%
- Take profit: +20%
- Time exit: 60 días

## Autor

MM - 2026-01-06
