from jinja2 import Template

TEMPLATE = Template("""
# Azure Waste Hunter — Weekly Cost Optimization Report

**Total Monthly Waste:** ${{ total }}

---

## Wasted Resources

{% for r in resources %}
### {{ r.type | upper }} — {{ r.name }}
- Location: {{ r.location }}
- Monthly Cost: ${{ r.monthly_cost }}
- Missing Tags: {{ r.tag_violations }}
{% if r.avg_cpu is defined %}
- Avg CPU: {{ r.avg_cpu }}%
{% endif %}
{% endfor %}

---

## Scan Errors
{% for e in scan_errors %}
- {{ e.stage }} → {{ e.error }}
{% endfor %}

---

## Delivery Errors
{% for e in delivery_errors %}
- {{ e.stage }} → {{ e.error }}
{% endfor %}
""")

def build_report(resources, scan_errors, delivery_errors):
    total = round(sum(r["monthly_cost"] for r in resources), 2)
    return TEMPLATE.render(
        resources=resources,
        total=total,
        scan_errors=scan_errors,
        delivery_errors=delivery_errors,
    )
