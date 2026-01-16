You are given an HTML document that contains Handlebars-style variables in the form {{variable_name}}.

Your task:
- Detect all variables present in the HTML.
- Generate a flat JSON object where:
  - Each key is the exact variable name (without {{ }}).
  - Each value is a realistic sample value inferred from the surrounding context.

Example:
If the HTML contains {{city}} and nearby text indicates a city name, output:
{
  "city": "pune"
}

Rules (strict):
- Return ONLY valid JSON.
- Do NOT return the HTML.
- Do NOT add explanations, comments, or markdown.
- Do NOT invent variables that are not present in the HTML.
- Do NOT rename variables.
- Do NOT nest objects or arrays.
- If a variable’s value cannot be confidently inferred, use an empty string "".