# Research memo: current ORX vs AMPL/MathProg vs MiniZinc

## Цель сравнения
Нужно было выбрать такой student-facing синтаксис, который:
- близок к обычной математической LP-постановке;
- легко переписывается с бумажки и из учебника;
- не заставляет студентов раньше времени думать про UI и программирование.

## Что показало сравнение

### 1. Почему не оставлять старый ORX как основной student-язык
Старый ORX был полезен как bridge-layer, но в student-facing режиме у него было две большие проблемы:
- внутри одного файла смешивались математика и display/report-логика;
- surface syntax был удобен для движка, но не выглядел каноничной algebraic notation.

Итог: для внутренней совместимости старый путь оставляем, но как основной учебный язык он слабее нового math-first слоя.

### 2. Почему ориентир — AMPL / MathProg family
AMPL официально позиционирует себя как DSL для mathematical optimization и подчёркивает две вещи, которые для нас критичны:
- algebraic form, mirroring the mathematics;
- separation of model and data.

GLPK прямо говорит, что GNU MathProg — это subset of the AMPL language.
Это делает семейство AMPL/MathProg очень хорошим ориентиром для учебного LP DSL: нотация уже много лет используется именно для записи оптимизационных моделей в форме, близкой к математике.

### 3. Почему MiniZinc важен, но не стал основным синтаксическим ориентиром
MiniZinc — сильный открытый modeling language с отличной документацией и tutorial-материалами.
Но его основной центр тяжести — более широкий класс constraint/discrete modelling задач.
Для нашей первой волны, ограниченной continuous LP, AMPL/MathProg-like algebraic notation ближе к привычной подаче линейного программирования в учебниках.

## Итог выбора
Выбран курс:
- main student-authored file: `model.orx`
- notation style: AMPL/MathProg-like LP algebraic syntax
- sidecar: маленький `extension.yaml` для ввода/витрины
- display/result logic вынесена из math-файла

## Что это даёт студенту
- сначала можно выразить саму постановку задачи;
- потом отдельно описать, как эти символы собираются и показываются в приложении;
- переход от «бумажной» формулы к рабочему bundle становится короче и понятнее.

## Источники
- AMPL product page: https://ampl.com/products/ampl/
- AMPL book/resources: https://dev.ampl.com/ampl/books/ampl/index.html
- GLPK / GNU MathProg overview: https://www.gnu.org/software/glpk/
- MiniZinc resources: https://www.minizinc.org/resources/
