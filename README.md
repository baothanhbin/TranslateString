# TranslateString

Tool Windows de dich Android `strings.xml` sang nhieu ngon ngu va xuat ra cac thu muc `values-*`.

## Tai ve va chay

Clone repo:

```powershell
git clone https://github.com/baothanhbin/TranslateString.git
cd TranslateString
```

Chay truc tiep file co san:

```text
dist\StringTranslator.exe
```

Sau khi mo tool:

1. Bam `Choose File` va chon file `strings.xml`.
2. Bam `Choose Folder` va chon thu muc output, thuong la thu muc `res`.
3. Tick cac ngon ngu can dich.
4. Bam `Translate`.

## Ngon ngu ho tro

- German: `values-de`
- Spanish: `values-es`
- English: `values-en`
- French: `values-fr`
- Hindi: `values-hi`
- Japanese: `values-ja`
- Korean: `values-ko`
- Portuguese: `values-pt`
- Russian: `values-ru`

Tool se bo qua string co `translatable="false"` va giu lai placeholder nhu `%1$s`, `%1$d%%`, `\n`, URL, inline XML tag nhu `<u>...</u>`.

## Tu build lai file exe

May can cai Python 3.11+.

Chay:

```powershell
.\build_exe.bat
```

File sau khi build nam tai:

```text
dist\StringTranslator.exe
```

## Chay bang command line

```powershell
python .\translate_strings.py .\strings.xml -o .\res
```

Dich mot vai ngon ngu:

```powershell
python .\translate_strings.py .\strings.xml -o .\res --locales de,es,en
```

Chi ro ngon ngu nguon:

```powershell
python .\translate_strings.py .\strings.xml -o .\res --source-lang en
```

## Ghi chu

Tool dang dung Google Translate public endpoint. Ket qua dich nen duoc review lai truoc khi dua vao production.

Cache dich duoc luu vao `.translate-cache.json` tren may local de lan sau chay nhanh hon. File cache nay khong can commit len git.
