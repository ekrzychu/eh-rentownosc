# EH Rentowność

A local Streamlit application for analysing the profitability of EH cases.

## Requirements

- Python 3
- `pip`
- A terminal / shell
- The project files, including `app.py` and `requirements.txt`

---

## Windows

### First-time setup

Open PowerShell in the project directory:

```powershell
cd H:\Projects\eh-rentownosc
```

Create a virtual environment:

```powershell
py -m venv .venv
```

Install the dependencies from `requirements.txt`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the application:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Using `python.exe -m streamlit` is the most reliable approach on Windows because it does not depend on `streamlit.exe` being available in the global `PATH`.

### Future runs

You do **not** need to reinstall the dependencies every time.

Open PowerShell and run:

```powershell
cd H:\Projects\eh-rentownosc
.\.venv\Scripts\python.exe -m streamlit run app.py
```

---

## Linux — Arch Linux

### First-time setup

Open a terminal and go to the project directory:

```bash
cd ~/path/to/eh-rentownosc
```

If Python is not installed:

```bash
sudo pacman -S python
```

Create a virtual environment:

```bash
python -m venv .venv
```

Install the dependencies:

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

Start the application:

```bash
./.venv/bin/python -m streamlit run app.py
```

### Future runs

You do **not** need to reinstall the dependencies every time.

Run:

```bash
cd ~/path/to/eh-rentownosc
./.venv/bin/python -m streamlit run app.py
```

---

## macOS

### First-time setup

Open Terminal and go to the project directory:

```bash
cd ~/path/to/eh-rentownosc
```

Check that Python 3 is available:

```bash
python3 --version
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Install the dependencies:

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

Start the application:

```bash
./.venv/bin/python -m streamlit run app.py
```

### Future runs

You do **not** need to reinstall the dependencies every time.

Run:

```bash
cd ~/path/to/eh-rentownosc
./.venv/bin/python -m streamlit run app.py
```

---

## Opening the application

After Streamlit starts, it will normally open the application automatically in your default browser.

If it does not, open the local address shown in the terminal, usually:

```text
http://localhost:8501
```

To stop the application, return to the terminal and press:

```text
Ctrl+C
```
