"""Legacy set-name <-> URL-slug encoding.

The Flask templates encoded set names into element ids / URL fragments with a
bespoke scheme, and ``api.apiGetCards`` reversed it:

    name -> slug :  ' ' -> '_'   "'" -> '8'   '?' -> '9'
    slug -> name :  '_' -> ' '   '8' -> "'"   '9' -> '?'

We preserve it exactly so any existing bookmarks/links keep resolving and so the
data (which embeds these characters in set names) is matched identically.
"""


def name_to_slug(name: str) -> str:
    return name.replace(" ", "_").replace("'", "8").replace("?", "9")


def slug_to_name(slug: str) -> str:
    return slug.replace("_", " ").replace("8", "'").replace("9", "?")
