# finance.categories

## Que hace

`finance.categories` administra el vocabulario de categorizacion financiera del
usuario o del sistema.

Su responsabilidad actual es simple:

- CRUD de categorias
- servir como referencia para transacciones, pagos y analitica

## Rol En El Producto

Las categorias permiten que Vexxo convierta movimientos en informacion util.

De cara al usuario, sostienen:

- clasificacion de gastos e ingresos
- reportes por categoria
- reglas o automatizaciones futuras
- mejor interpretacion en dashboard, alertas y recomendaciones

## Flujo Principal

1. el usuario o backoffice crea/edita una categoria
2. `transactions` y otros contextos pueden referenciarla
3. reportes y analitica agrupan resultados usando esa semantica

## Relacion Con Otros Modulos

- `finance.transactions`
  usa categoria como parte del ledger y del reporting
- `payments`
  puede propagar categoria sugerida a intents o templates
- `reports`
  agrupa gasto por categoria

## Encaje Con GCP

Es un modulo OLTP liviano sobre Cloud SQL y BFF en Cloud Run.

No requiere procesamiento largo ni pipelines propios, pero su semantica impacta
los datos que luego llegan a BigQuery y reportes.

## Estado Actual

Hoy expone un `ModelViewSet` basico (`CategoriaViewSet`) sobre `Category`.

Es una capa CRUD sencilla, pero funcionalmente importante porque aporta
semantica al resto del producto.
