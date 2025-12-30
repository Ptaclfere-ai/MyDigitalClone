import docx

# Use absolute path just to be safe, though relative should work if CWD is correct.
# The error was "Access denied. Edit operations are restricted to the working directory."
# The previous `Write` used `file_path: debug_docx.py` which implied CWD.
# I will use the full path this time.

file_path = r"c:\Users\wyb01\Desktop\PycharmProjects\pycharmProject\小程序\weichat\PyWxDumpMini-main\yyl.docx"
doc = docx.Document(file_path)

print("--- First 20 Paragraphs of yyl.docx ---")
for i, para in enumerate(doc.paragraphs[:20]):
    if para.text.strip():
        print(f"[{i}] {para.text}")
print("--- End ---")
