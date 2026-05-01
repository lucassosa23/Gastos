# Gastitos · Control de Gastos Personales

> Aplicación web para llevar el control de gastos personales del día a día. Built with Django.

[![CI](https://github.com/lucassosa23/Gastos/actions/workflows/ci.yml/badge.svg)](https://github.com/lucassosa23/Gastos/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Django](https://img.shields.io/badge/Django-5.2.5-092E20?logo=django&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

> 🔗 **Demo en vivo:** _en preparación — se actualiza cuando se complete el deploy._

<!--
  HERO SCREENSHOT
  Reemplazar por una captura del dashboard o del home.
  Sugerencia: docs/screenshots/hero.png a 1280×720.
-->
<!-- ![Gastitos hero](docs/screenshots/hero.png) -->

---

## Por qué construí esto

Necesitaba una herramienta para llevar el control económico real de mi día a día — algo que reflejara salario, saldo disponible, gastos fijos y planificación, sin atarme a una app comercial. En paralelo, lo aproveché como vehículo para profundizar en **Django** (App-router en su flavor moderno, ORM, migrations, ModelForms), patrones de **service layer**, manejo correcto de **Decimal** en finanzas, y prácticas de seguridad web (CSP, CSRF, atomicidad, sanitización XSS).

El proyecto pasó por una auditoría de seguridad y refactor profundo para llegar a su estado actual — ver [Decisiones clave](#decisiones-clave) para los puntos más interesantes.

---

## Features

- **Registro y categorización de gastos** con soporte para subir comprobantes (imagen) y extracción automática de monto/fecha vía OCR (Tesseract).
- **Procesamiento de estados de cuenta de tarjeta** (PDF) con extracción de total agregado.
- **Gastos fijos recurrentes** (servicios, alquiler, suscripciones) que se aplican con un click.
- **Planificación de gastos** del mes siguiente con saldo personalizado + monto sobrante.
- **Modo Ahorro**: metas con monto objetivo, fecha límite y cálculo de ahorro mensual/semanal recomendado.
- **Vencimientos** con alertas dentro de los próximos 3 días.
- **Dashboard** con saldo del mes, gasto disponible por fin de semana restante, calendario de gastos, gráficos de evolución y resumen de los últimos 6 meses.

---

## Tech stack

| Capa | Tecnología |
|---|---|
| Framework | Django 5.2 (Python 3.13) |
| Database | SQLite (dev) / PostgreSQL-ready |
| Frontend | Django templates + Bootstrap 5 + Chart.js |
| OCR | Tesseract (vía `pytesseract`) + OpenCV + Pillow |
| Auth | Django auth + sessions |
| CI | GitHub Actions (check + migrate + tests + deploy-check) |

---

## Arquitectura

```
gastitos/                # App principal
├── models.py            # PerfilUsuario · Gasto · GastoFijo · GastoPlanificado
│                        # Vencimiento · MetaAhorro · EstadisticaMensual
├── views.py             # Vistas controller-thin (auth + render)
├── forms.py             # ModelForms con clean_* para validación
├── services/
│   └── dashboard.py     # Lógica de negocio del dashboard extraída
├── utils.py             # OCR, validación de uploads, helpers
├── utils_ahorro.py      # Lógica del modo ahorro
├── utils_estadisticas.py
├── tests.py             # 14 tests: auth, CRUD, IDOR, service layer
└── migrations/

gastos/                  # Configuración Django
├── settings.py          # Env vars + security headers
└── urls.py

templates/
├── base.html
├── dashboard.html       # JSON-script tag para data del calendario
├── gastos/              # Forms y vistas autenticadas
└── gastitos/            # Modo ahorro y planificación

.github/workflows/
└── ci.yml               # CI en cada push/PR
```

### Decisiones clave

- **`Decimal` end-to-end** — el modelo guarda `DecimalField` y todos los cálculos de saldo (suma, resta, división, porcentaje) usan `Decimal` para evitar pérdida de centavos. Solo al serializar arrays de Chart.js se convierte a `float`.
- **`transaction.atomic` + `select_for_update`** en operaciones de saldo — evita race conditions cuando dos requests del mismo usuario consumen saldo en paralelo.
- **Service layer** — la vista `dashboard()` se redujo de ~180 LOC a ~50 LOC extrayendo la lógica a `services/dashboard.py` con seis funciones puras y testeables.
- **Defensa XSS en dos capas** — backend usa el filtro nativo `json_script` de Django para inyectar JSON en `<script>`; frontend usa `createElement` + `textContent` en lugar de `innerHTML` cuando renderiza data del usuario.
- **Validación de uploads** — todo `request.FILES` pasa por `validate_image_upload` / `validate_pdf_upload` que restringen tipo MIME, extensión y tamaño máximo (5 MB / 10 MB), y `randomize_filename` para evitar colisiones y filtrar el nombre original del cliente.
- **Settings via env vars con modo estricto** — en producción (`DJANGO_DEBUG=False`) se levanta `RuntimeError` si falta `DJANGO_SECRET_KEY`. En desarrollo cae a un fallback obvio.

---

## Setup local

**Requisitos:** Python 3.11+ (probado con 3.13), Tesseract OCR si se va a usar la extracción de imágenes.

```bash
# 1. Clonar
git clone https://github.com/lucassosa23/Gastos.git
cd Gastos

# 2. Crear entorno virtual e instalar dependencias
python -m venv .venv
source .venv/bin/activate           # Linux/macOS
# .venv\Scripts\activate            # Windows
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env y poner una SECRET_KEY real:
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 4. Aplicar migraciones y arrancar
python manage.py migrate
python manage.py createsuperuser    # opcional, para acceder al /admin/
python manage.py runserver
```

Abrir [http://localhost:8000](http://localhost:8000).

---

## Tests

```bash
python manage.py test gastitos -v 2
```

14 tests cubriendo:
- Auth flow (redirect sin login, vistas protegidas).
- Gastos CRUD (alta con `Decimal` preservado, saldo insuficiente, edición con monto inválido).
- IDOR (un usuario no puede modificar gastos de otro).
- Service layer del dashboard (las 6 funciones extraídas).

---

## CI

GitHub Actions corre en cada push a `main` y en cada PR:

1. `manage.py check` — system check de Django.
2. `manage.py migrate` sobre DB vacía — verifica que la cadena de migraciones aplica desde cero.
3. `manage.py test gastitos -v 2` — los 14 tests.
4. `manage.py check --deploy` — modo producción, valida headers de seguridad.

---

## Screenshots

<!--
  Sustituir por capturas reales:
    docs/screenshots/home.png
    docs/screenshots/dashboard.png
    docs/screenshots/calendario.png
    docs/screenshots/modo-ahorro.png
-->

| Home | Dashboard |
|---|---|
| _<!-- ![Home](docs/screenshots/home.png) -->_ | _<!-- ![Dashboard](docs/screenshots/dashboard.png) -->_ |

| Calendario | Modo Ahorro |
|---|---|
| _<!-- ![Calendario](docs/screenshots/calendario.png) -->_ | _<!-- ![Modo Ahorro](docs/screenshots/modo-ahorro.png) -->_ |

---

## Roadmap

- [x] Auth + perfil + salario configurable
- [x] Gastos diarios + edición + eliminación
- [x] Gastos fijos recurrentes
- [x] Procesamiento OCR de comprobantes y estados de cuenta
- [x] Calendario de gastos
- [x] Modo Ahorro (metas con fecha límite)
- [x] Planificación del mes siguiente
- [x] Auditoría de seguridad completa (XSS, IDOR audit, race conditions, validación de uploads)
- [x] Suite de tests + CI
- [ ] Deploy a producción (Railway / Fly.io)
- [ ] Migración a PostgreSQL en producción
- [ ] Validación de teléfono país-agnóstica (actualmente asume formato chileno)
- [ ] Internacionalización i18n (actualmente solo español)

---

## Autor

**Lucas Sosa** · [GitHub](https://github.com/lucassosa23) · [Portfolio](https://github.com/lucassosa4)

Si encontrás algo para mejorar o querés sugerir una feature, abrí un issue.

---

## Licencia

MIT — ver [LICENSE](LICENSE) si está presente, o usar libremente con atribución.
