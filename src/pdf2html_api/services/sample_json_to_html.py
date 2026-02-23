from bs4 import BeautifulSoup, NavigableString


def apply_sample_json_to_html(html: str, sample_json: dict) -> str:
    soup = BeautifulSoup(html, "lxml")

    # Only walk visible text nodes in body
    for text_node in soup.body.descendants:
        if not isinstance(text_node, NavigableString):
            continue

        original_text = text_node.strip()
        if not original_text:
            continue

        for key, value in sample_json.items():
            if value == original_text:
                text_node.replace_with(f"{{{{{key}}}}}")
                break  # one replacement per node

    return str(soup)