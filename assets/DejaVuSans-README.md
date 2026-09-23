# Bundled PDF font

`DejaVuSans.ttf` is the unmodified DejaVu Sans 2.37 font. The PDF exporter
loads this repository asset before checking system fonts, so Windows and CI
use the same font without a separate download or OS font installation.
It includes the Kazakh and Russian Cyrillic characters used by the project.

Upstream project: https://dejavu-fonts.github.io/
Vendored from the local Poppler runtime font distribution. Version and license
were read directly from the font's embedded name table. The full embedded
copyright and license notices are included in `DejaVuSans-LICENSE.txt`.
Keep that license with the font when distributing the application.

SHA-256: `7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954`
