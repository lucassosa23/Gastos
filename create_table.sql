DROP TABLE IF EXISTS "gastitos_gastoplanificado";

CREATE TABLE IF NOT EXISTS "gastitos_gastoplanificado" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "descripcion" varchar(200) NOT NULL,
    "monto" decimal NOT NULL,
    "mes" integer NOT NULL,
    "anio" integer NOT NULL,
    "fecha_creacion" datetime NOT NULL,
    "completado" bool NOT NULL,
    "usuario_id" integer NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
);