# Repara la migración 0012_add_saldo_base, que usaba
# SeparateDatabaseAndState con database_operations=[] y por eso nunca
# emitió el ALTER TABLE real. Sobre cualquier DB nueva el modelo declara
# el campo `saldo_base` pero la columna no existe.
#
# Esta migración es idempotente: si la columna ya está (por ejemplo en
# DBs donde se agregó manualmente fuera del flujo de Django) no toca
# nada. Si no está, la crea.

from django.db import migrations


def add_saldo_base_if_missing(apps, schema_editor):
    table = 'gastitos_perfilusuario'
    column = 'saldo_base'
    with schema_editor.connection.cursor() as cursor:
        existing = {row[1] for row in cursor.execute(f'PRAGMA table_info({table})').fetchall()} \
            if schema_editor.connection.vendor == 'sqlite' \
            else {row[0] for row in cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                [table],
            ).fetchall()}
        if column not in existing:
            cursor.execute(
                f'ALTER TABLE {table} '
                f'ADD COLUMN {column} numeric(10, 2) NULL'
            )


def noop(apps, schema_editor):
    # No se elimina la columna en el reverse: el campo sigue declarado
    # en el modelo y removerla rompería el state.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gastitos', '0015_create_gastoplanificado_table'),
    ]

    operations = [
        migrations.RunPython(add_saldo_base_if_missing, noop),
    ]
