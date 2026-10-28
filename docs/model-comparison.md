# Rewrite comparison: llama3.2 vs qwen3.5:4b

Generated with `tools/eval_rewrite.py llama3.2 qwen3.5:4b --runs 3` on an RTX 3060 Laptop GPU (6 GB VRAM), using the default prompt and temperature 0.2. Each model rewrote each transcript 3 times. A run passes when it follows the template, keeps every required detail, puts tech constraints and ambiguities in the right sections, and drops filler words without inventing anything. The outputs below are the first run of each.

| Model | Passed | Avg time | Memory |
|---|---|---|---|
| llama3.2 | 7/9 | 0.68s | 2.6 GB, 100% on GPU |
| qwen3.5:4b | 9/9 | 1.28s | 3.1 GB, 100% on GPU |

## 1. Self-corrections and sizes

**Before (transcript):**

> um okay so on the home page the, the big title, make it, like, red, no actually dark green, and uh make it a bit bigger, maybe 48 pixels, and move the sign up button so it's like under the title instead of on the right

**After - llama3.2** (0.5s) ✅

```
Goal: Modify the home page layout.
Features:
- Change the big title color to "dark green".
- Increase the title size to 48 pixels.
- Move the sign up button below the title instead of on the right.
```

**After - qwen3.5:4b** (1.22s) ✅

```
Goal: Update the home page styling and layout.
Features:
- Change the big title color to dark green.
- Increase the big title size to 48 pixels.
- Move the sign up button to be under the title instead of on the right.
```


## 2. Feature with tech constraints

**Before (transcript):**

> so I want to add, um, a dark mode, you know, a toggle in the top right corner, and it should remember what you picked, like save it in local storage I think, and uh don't use any new libraries, just plain CSS, and oh also the footer text should say Made with love in Amsterdam

**After - llama3.2** (0.81s) ✅

```
Goal: Add a dark mode toggle to the top right corner of the page.
Features:
- Add a dark mode toggle.
- Save the user's preference in local storage.
- Implement the dark mode using plain CSS.
- Update the footer text to "Made with love in Amsterdam".
Tech/Constraints:
- Do not use any new libraries.
Notes:
- "Plain CSS" was not further described.
```

**After - qwen3.5:4b** (1.42s) ✅

```
Goal: Add a dark mode toggle to the top right corner that saves its state in local storage.
Features:
- Add a dark mode toggle in the top right corner.
- Save the toggle state in local storage.
- Change the footer text to "Made with love in Amsterdam".
Tech/Constraints:
- Use plain CSS only; do not use any new libraries.
```


## 3. Vague request with false starts

**Before (transcript):**

> hey so the uh, the map thing, the map page, it's kind of slow when you, when you zoom in, can you make it faster, and maybe add like a search bar, a search bar where you type a city and it jumps there, and um I'm not sure about the colours, maybe change them, whatever looks better

**After - llama3.2** (0.75s) ✅

```
Goal: Improve the map page's performance and add a search bar.
Features:
- Make the map page faster when zooming in.
- Add a search bar that jumps to a city when a city is typed.
- Change the colours to something that looks better.
Notes:
- The exact colours to change were not specified.
```

**After - qwen3.5:4b** (1.58s) ✅

```
Goal: Improve the performance of the map page when zooming in and add a search bar to jump to cities.
Features:
- Make the map page faster when zooming in.
- Add a search bar where typing a city jumps to that location.
Notes:
- The specific colours to change were not defined; "whatever looks better" was not described further.
```
