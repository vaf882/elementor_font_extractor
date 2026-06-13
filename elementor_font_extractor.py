#!/usr/bin/env python3
"""
Elementor Font Extractor & Replacer

Рекурсивно сканирует текущую папку и все подпапки,
ищет в JSON-шаблонах Elementor используемые шрифты.
Заменяет шрифты по таблице из внешнего файла.

Использование:
    # Только сканирование:
    python elementor_font_extractor.py

    # Сканирование + замена:
    python elementor_font_extractor.py --map fonts_map.txt

    # Пробный прогон (без записи файлов):
    python elementor_font_extractor.py --map fonts_map.txt --dry-run

Формат файла замен (fonts_map.txt):
    # Комментарии начинаются с #
    Старый шрифт=Новый шрифт
    Bree Serif=PT Serif
    Figtree=Manrope
"""

import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict


def load_replacements(map_file):
    path = Path(map_file)
    if not path.exists():
        print("[ERROR] Файл таблицы замен не найден: " + map_file, file=sys.stderr)
        sys.exit(1)
    replacements = {}
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                print("  [WARN] Строка " + str(line_num) + " пропущена (нет '='): " + line, file=sys.stderr)
                continue
            old, new = line.split("=", 1)
            replacements[old.strip()] = new.strip()
    print("  Загружено " + str(len(replacements)) + " правил замены из: " + map_file + "\n")
    return replacements


# Ловим любой ключ оканчивающийся на _font_family или FontFamily
# Примеры:
#   "typography_font_family": "Bree Serif"
#   "archive_cards_title_typography_font_family": "Bree Serif"
#   "typographyFontFamily": "Bree Serif"
FONT_RE = re.compile(
    r'("[^"]*(?:_font_family|FontFamily|font_family)"\s*:\s*")([^"]+)(")',
    re.IGNORECASE,
)


def extract_fonts(filepath):
    fonts = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
        for m in FONT_RE.finditer(raw):
            fonts.add(m.group(2).strip())
    except (OSError, UnicodeDecodeError) as e:
        print("  [WARN] Не удалось прочитать " + str(filepath) + ": " + str(e), file=sys.stderr)
    return fonts


def replace_fonts_in_file(filepath, replacements, dry_run):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print("  [WARN] Не удалось прочитать " + str(filepath) + ": " + str(e), file=sys.stderr)
        return []

    changes = []
    for old_font, new_font in replacements.items():
        pattern = re.compile(
            r'("[^"]*(?:_font_family|FontFamily|font_family)"\s*:\s*")'
            + re.escape(old_font) + r'(")',
            re.IGNORECASE,
        )
        new_content, count = pattern.subn(
            lambda m, nf=new_font: m.group(1) + nf + m.group(2),
            content,
        )
        if count > 0:
            changes.append((old_font, new_font, count))
            content = new_content

    if changes and not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return changes


def scan(replacements, dry_run):
    root = Path.cwd()

    font_to_files = defaultdict(set)
    replaced_in = defaultdict(set)
    replacements_log = {}

    mode = ""
    if replacements:
        mode = " [ПРОБНЫЙ ПРОГОН]" if dry_run else " [ЗАМЕНА ВКЛЮЧЕНА]"

    print("Сканирование: " + str(root) + mode)
    print("-" * 60)

    for json_file in sorted(root.rglob("*.json")):
        rel = json_file.relative_to(root)
        fonts = extract_fonts(json_file)
        if not fonts:
            continue

        print("  v  " + str(rel))
        for font in sorted(fonts):
            font_to_files[font].add(str(rel))
            print("       -- " + font)

        if replacements:
            changes = replace_fonts_in_file(json_file, replacements, dry_run)
            if changes:
                replacements_log[str(rel)] = changes
                for old, new, count in changes:
                    tag = "(не записано)" if dry_run else "(записано)"
                    print("       -> " + old + "  =>  " + new + "  x" + str(count) + "  " + tag)
                    replaced_in[old].add(str(rel))

    print("-" * 60)
    return dict(font_to_files), dict(replaced_in), replacements_log


def print_summary(font_to_files, replaced_in, replacements_log, replacements, dry_run):
    all_fonts = sorted(font_to_files.keys())

    if not all_fonts:
        print("\n[!] Шрифты не найдены ни в одном файле.")
        return

    print("\n" + "=" * 60)
    print("  НАЙДЕНО ШРИФТОВ: " + str(len(all_fonts)))
    print("=" * 60)
    for font in all_fonts:
        files = sorted(font_to_files[font])
        print("\n  [font]  " + font + "  (" + str(len(files)) + " файл(ов))")
        for f in files:
            print("          * " + f)

    if replacements and replacements_log:
        total = sum(sum(c for _, _, c in v) for v in replacements_log.values())
        print("\n" + "=" * 60)
        print("  ИТОГ ЗАМЕН: " + str(total) + " замен в " + str(len(replacements_log)) + " файл(ах)")
        if dry_run:
            print("  (файлы НЕ изменены -- пробный прогон)")
        print("=" * 60)
        for filepath, changes in sorted(replacements_log.items()):
            print("\n  [файл]  " + filepath)
            for old, new, count in changes:
                print("       " + old.ljust(35) + " =>  " + new + "  x" + str(count))

    print("\n" + "=" * 60)
    if replacements:
        print("  СТАТУС ЗАМЕНЫ ШРИФТОВ")
    else:
        print("  ВСЕ НАЙДЕННЫЕ ШРИФТЫ")
    print("=" * 60)

    replaced_fonts = []
    not_replaced_fonts = []
    for font in all_fonts:
        if replacements and font in replacements:
            replaced_fonts.append((font, replacements[font]))
        else:
            not_replaced_fonts.append(font)

    if replaced_fonts:
        print("\n  [OK] Заменены (" + str(len(replaced_fonts)) + "):")
        for old, new in replaced_fonts:
            print("       " + old.ljust(35) + " =>  " + new)

    if not_replaced_fonts:
        if replacements:
            label = "Не заменены -- нет в таблице замен"
        else:
            label = "Найденные шрифты"
        print("\n  [!] " + label + " (" + str(len(not_replaced_fonts)) + "):")
        for font in not_replaced_fonts:
            print("       " + font)

    if not replacements:
        print("\n  Подсказка: запустите с --map fonts_map.txt для замены шрифтов")


def main():
    parser = argparse.ArgumentParser(
        description="Elementor Font Extractor & Replacer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--map", metavar="FILE",
        help="Файл таблицы замен (формат: Старый=Новый, по одному в строке)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Пробный прогон: показать что изменится, но не записывать файлы",
    )
    args = parser.parse_args()

    replacements = {}
    if args.map:
        replacements = load_replacements(args.map)

    font_to_files, replaced_in, replacements_log = scan(
        replacements=replacements,
        dry_run=args.dry_run,
    )
    print_summary(font_to_files, replaced_in, replacements_log, replacements, args.dry_run)


if __name__ == "__main__":
    main()
