# Third-Party Notices

节碳家运行与构建使用以下第三方资源。完整许可文本以各依赖包发行版为准。

## Runtime

| Component | Version | License | Usage |
|---|---:|---|---|
| Python | 3.12+ | PSF License | Runtime |
| Flask | 3.1.3 | BSD-3-Clause | Web framework |
| flask-cors | 6.0.5 | MIT | Optional local cross-origin debugging |
| Werkzeug | 3.1.9 (indirect) | BSD-3-Clause | WSGI and password utilities |
| Jinja2 | 3.1.6 (indirect) | BSD-3-Clause | Flask dependency, no custom templates |
| Click | 8.5.1 (indirect) | BSD-3-Clause | Flask dependency |
| itsdangerous | 2.2.0 (indirect) | BSD-3-Clause | Flask dependency |
| MarkupSafe | 3.0.4 (indirect) | BSD-3-Clause | Flask dependency |
| Blinker | 1.9.0 (indirect) | MIT | Flask dependency |
| SQLite | Python standard library | Public Domain | Local account and carbon record storage |
| Gunicorn | 23.0.0 | MIT | Production WSGI server |

## Development and validation

| Component | License | Usage |
|---|---|---|
| Node.js | MIT | Front-end static tests |
| Microsoft Edge / Chromium | Third-party license | Local headless visual and interaction checks |

## Remote AI services

The application supports OpenAI-compatible APIs selected and paid for by the user. No vendor API key is distributed. Requests are subject to the selected provider's terms and privacy policy. AI output is used only for explanatory text and is validated by the application.

## Fonts and visual assets

The interface uses operating-system font fallbacks and self-drawn inline SVG/CSS. No third-party icon library, brand logo, remote font, image library or CDN resource is bundled.

## Data provenance

The electricity carbon-footprint factor and Shaanxi residential tariff derive from official public sources recorded in `docs/数据来源.md`. The Xi'an appliance trade-in policy is linked to the Xi'an Municipal Bureau of Commerce and is displayed only as a candidate match.

Measure-level electricity-saving values are a mixture of public-reference calculations, national-standard calculations and engineering estimates. Values not backed by household measurement are labelled as estimates in the interface and must not be represented as verified savings or government statistics.
