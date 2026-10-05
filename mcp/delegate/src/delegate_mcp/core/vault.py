TEMPLATE_BY_FOLDER = {
    "wiki/": "wiki",
    "investigations/": "investigation",
    "projects/": "project",
    "plans/": "plan-index",
    "meetings/": "meeting-one-on-one",
}


def template_stem(relative_path: str, template_name: str) -> str:
    """The template to use: the one named, else the one for the page's top folder."""
    if template_name:
        return template_name
    for folder, stem in TEMPLATE_BY_FOLDER.items():
        if relative_path.startswith(folder):
            return stem
    return ""
