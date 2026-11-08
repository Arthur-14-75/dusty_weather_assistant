from pathlib import Path
import markdown
from weasyprint import HTML, CSS

def generate_analysis_report(report_markdown:str, departure:str, destination:str)->str:
    "Cette fonction permet de convertir le markdown généré par la fonction evaluate_flight_feasibility_node "
    "en un rapport PDF structuré et lisible."

    reports_directory = Path("bulletins_analyses_pdf")
    reports_directory.mkdir(parents=True, exist_ok=True)
    pdf_path = reports_directory / f"rapport_prevol_{departure}_{destination}.pdf"

    #Conversion du markdown en HTML
    html_content = markdown.markdown(report_markdown, extensions=['tables', 'fenced_code', 'toc'])

    #Création du PDF à partir du HTML
    full_html = f"""
            <!DOCTYPE html>
            <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <style>
                    @page {{
                        size: A4;
                        margin: 20mm;
                    }}
                    body {{
                        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                        color: #2c3e50;
                        line-height: 1.5;
                        font-size: 11pt;
                    }}
                    h1 {{
                        color: #1a365d;
                        border-bottom: 2px solid #2b6cb0;
                        padding-bottom: 8px;
                        font-size: 18pt;
                    }}
                    h2 {{
                        color: #2b6cb0;
                        margin-top: 18px;
                        font-size: 14pt;
                    }}
                    h3 {{
                        color: #4a5568;
                        font-size: 12pt;
                        margin-bottom: 4px;
                    }}
                    blockquote {{
                        background-color: #f7fafc;
                        border-left: 4px solid #cbd5e0;
                        margin: 0;
                        padding: 10px 15px;
                        font-family: monospace;
                        font-size: 10pt;
                    }}
                    .badge-go {{
                        color: #22543d;
                        background-color: #c6f6d5;
                        padding: 4px 8px;
                        border-radius: 4px;
                    }}
                    .badge-nogo {{
                        color: #742a2a;
                        background-color: #fed7d7;
                        padding: 4px 8px;
                        border-radius: 4px;
                    }}
                </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
        """
    HTML(string=full_html).write_pdf(pdf_path)
    return str(pdf_path)
