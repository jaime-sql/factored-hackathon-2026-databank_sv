# ¿Cómo funciona?

Texto de la guía para el video. La fuente es `GUIDE` en `static/js/tour.js`.

Controles: Anterior / Siguiente / Cerrar. El contador se ve como 2/7. Esc cierra.
PT: Anterior / Seguinte / Fechar.
Si el elemento no está en pantalla: «aparece cuando hay casos».
PT: «aparece quando há casos».

## Cliente (`/`)

### 1. `a[href="/"]`

Esta pantalla es la del cliente: aquí se elige un cargo y se abre el caso.

PT: Esta é a tela do cliente: aqui se escolhe uma cobrança e se abre o caso.

### 2. `a[href="/agent"]`

Consola abre la cola de la persona que revisa los casos.

PT: Consola abre a fila da pessoa que revisa os casos.

### 3. `a[href="/metrics"]`

Métricas abre el tablero de conteos.

PT: Métricas abre o painel de contagens.

### 4. `#lang`

Este botón cambia el idioma entre español y portugués.

PT: Este botão muda o idioma entre espanhol e português.

### 5. `#tour`

Este botón abre la guía y también la cierra.

PT: Este botão abre o guia e também o fecha.

### 6. `#personas [data-action="persona"]`

Elija una persona sintética para ver sus cargos.

PT: Escolha uma pessoa sintética para ver as cobranças dela.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 7. `#charges [data-action="select-charge"]`

Este botón elige el cargo que la persona no reconoce.

PT: Este botão escolhe a cobrança que a pessoa não reconhece.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 8. `#message`

Escriba aquí un mensaje sobre el cargo.

PT: Escreva aqui uma mensagem sobre a cobrança.

### 9. `#send`

Enviar entrega ese mensaje al asistente.

PT: Enviar entrega essa mensagem ao assistente.

### 10. `details.why summary`

¿Por qué? muestra la hora local, la banda y el motivo.

PT: Por quê? mostra a hora local, a faixa e o motivo.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 11. `#thread [data-action="confirm_block"]`

Puntaje de fraude mayor a 30. Se bloquea la tarjeta y el caso pasa a una persona.

PT: Pontuação de fraude maior que 30. O cartão é bloqueado e o caso passa a uma pessoa.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 12. `#thread [data-action="decline_block"]`

Si no confirma, la tarjeta no se bloquea.

PT: Se não confirmar, o cartão não é bloqueado.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 13. `#thread [data-action="contest"]`

Este botón pide que una persona revise un cargo pendiente o revertido.

PT: Este botão pede que uma pessoa revise uma cobrança pendente ou revertida.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 14. `#thread [data-action="recognize"]`

Este botón indica que el cliente reconoce el cargo.

PT: Este botão indica que o cliente reconhece a cobrança.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 15. `#thread [data-action="open_dispute"]`

Riesgo bajo. El sistema explica el cargo, y el cliente puede pedir hablar con una persona.

PT: Risco baixo. O sistema explica a cobrança, e o cliente pode pedir para falar com uma pessoa.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 16. `#thread [data-band="review"]`

El modelo no puede descartar fraude, así que una persona revisa el cargo.

PT: O modelo não pode descartar fraude, então uma pessoa revisa a cobrança.

Dinámico. Si no está en pantalla: aparece cuando hay casos

## Consola (`/agent`)

### 1. `a[href="/"]`

Cliente vuelve a la pantalla donde se abre un caso.

PT: Cliente volta à tela onde se abre um caso.

### 2. `a[href="/agent"]`

Esta pantalla es la consola: la cola de casos para una persona.

PT: Esta tela é a consola: a fila de casos para uma pessoa.

### 3. `a[href="/metrics"]`

Métricas abre el tablero de conteos.

PT: Métricas abre o painel de contagens.

### 4. `#lang`

Este botón cambia el idioma entre español y portugués.

PT: Este botão muda o idioma entre espanhol e português.

### 5. `#tour`

Este botón abre la guía y también la cierra.

PT: Este botão abre o guia e também o fecha.

### 6. `#token`

Escriba el token del agente para leer la cola.

PT: Escreva o token do agente para ler a fila.

### 7. `#load`

Ver cola pide los casos que esperan a una persona.

PT: Ver cola pede os casos que esperam uma pessoa.

### 8. `#queue article.card`

Cada tarjeta muestra la banda, el monto, el comercio enmascarado, la hora local y el motivo.

PT: Cada cartão mostra a faixa, o valor, o comércio mascarado, a hora local e o motivo.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 9. `#queue [data-action="packet"]`

Abrir paquete muestra el caso verificado, sin el texto crudo del cliente.

PT: Abrir paquete mostra o caso verificado, sem o texto cru do cliente.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 10. `#queue [data-action="resolve"]`

Resolver cierra ese caso en la cola.

PT: Resolver fecha esse caso na fila.

Dinámico. Si no está en pantalla: aparece cuando hay casos

## Métricas (`/metrics`)

### 1. `a[href="/"]`

Cliente abre la pantalla donde se elige un cargo.

PT: Cliente abre a tela onde se escolhe uma cobrança.

### 2. `a[href="/agent"]`

Consola abre la cola de la persona que revisa los casos.

PT: Consola abre a fila da pessoa que revisa os casos.

### 3. `a[href="/metrics"]`

Esta pantalla es el tablero de conteos.

PT: Esta tela é o painel de contagens.

### 4. `#lang`

Este botón cambia el idioma entre español y portugués.

PT: Este botão muda o idioma entre espanhol e português.

### 5. `#tour`

Este botón abre la guía y también la cierra.

PT: Este botão abre o guia e também o fecha.

### 6. `#include-eval`

Este interruptor incluye o deja fuera los casos de evaluación.

PT: Este interruptor inclui ou deixa de fora os casos de avaliação.

### 7. `[data-metric="cases"]`

Esta ficha cuenta los casos que entran en el tablero.

PT: Este cartão conta os casos que entram no painel.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 8. `[data-metric="handoff"]`

Esta ficha mide la proporción de casos cerrados que pasaron a una persona.

PT: Este cartão mede a proporção de casos fechados que passaram a uma pessoa.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 9. `[data-metric="containment"]`

Esta ficha mide la proporción de casos cerrados que no pasaron a una persona.

PT: Este cartão mede a proporção de casos fechados que não passaram a uma pessoa.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 10. `[data-metric="eval"]`

Esta ficha cuenta los casos de evaluación que quedaron fuera de estas cifras.

PT: Este cartão conta os casos de avaliação que ficaram fora destas cifras.

Dinámico. Si no está en pantalla: aparece cuando hay casos

### 11. `#raw`

Este bloque es el mismo cálculo en JSON, para leer el detalle.

PT: Este bloco é o mesmo cálculo em JSON, para ler o detalhe.

