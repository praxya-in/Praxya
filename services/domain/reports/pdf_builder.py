from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent / 'templates'

def render_brsr_pdf(context: dict) -> bytes:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template('brsr_section_c_p9.html.j2')
    html_str = template.render(**context)
    return HTML(string=html_str).write_pdf()
