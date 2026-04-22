# Research memo: Lark vs textX vs ANTLR for this project

## Задача выбора
Нужен parser stack, который:
- естественно живёт в Python-проекте;
- поддерживает внешние grammar-файлы;
- позволяет держать грамматику как first-class артефакт репозитория;
- не перегружает учебный проект слишком тяжёлым toolchain.

## Lark
Что понравилось:
- grammar syntax based on EBNF;
- поддержка `%import` и grammar composition;
- templates в grammar-level;
- естественная работа внутри Python без отдельного code-generation build-step.

Для нас это даёт хороший баланс между прозрачностью grammar-файлов и лёгкостью интеграции в существующий код.

## textX
textX силён как grammar -> metamodel инструмент.
Официальная документация прямо подчёркивает, что каждая grammar-rule может становиться Python-class внутри meta-model.

Это очень полезный референс для архитектуры metamodel, но как основной стек мы его не выбрали по двум причинам:
- у нас уже был рабочий Lark-контур;
- нам нужен был мягкий migration path без полной смены parsing-подсистемы.

Итог: textX используем как архитектурный ориентир для explicit metamodel discipline, но не как основную runtime-библиотеку.

## ANTLR
ANTLR — мощный и широко используемый parser generator.
Но для текущего проекта он тяжелее по toolchain и operational overhead, чем нужно:
- отдельный generation workflow;
- более тяжёлая интеграция в компактный Python-first stack;
- избыточность для первой очереди LP-focused student DSL.

Итог: ANTLR остаётся запасным сильным вариантом, но не выбран для первой волны redesign.

## Принятое решение
Выбран стек:
- `Lark`
- external `.lark` grammar files in repo
- explicit metamodel / AST layer в Python

Это даёт:
- прозрачные grammar-файлы;
- достаточно лёгкую интеграцию;
- хороший фундамент для дальнейших преобразований `grammar -> AST -> solver IR`.

## Дополнительные project references
- Lark repo: https://github.com/lark-parser/lark
- textX repo: https://github.com/textX/textX
- ANTLR4 repo: https://github.com/antlr/antlr4

## Источники
- Lark grammar reference: https://lark-parser.readthedocs.io/en/stable/grammar.html
- textX metamodel docs: https://textx.github.io/textX/metamodel.html
- ANTLR overview: https://www.antlr.org/about.html
