import pandas as pd
import os
import sys


def load_books(file_path, mode='isbn'):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return []

    try:
        df = _read_csv_any_encoding(file_path)
        df.columns = df.columns.str.strip()

        books_list = []
        
        if mode == 'isbn':
            isbn_col = next((col for col in df.columns if 'isbn13' in col.lower()), None)
            
            if not isbn_col:
                print(f"Error: No column with 'ISBN' found in {file_path}")
                return []
            
            df['Identifier'] = df[isbn_col].fillna('').astype(str)
            df['Identifier'] = df['Identifier'].str.replace('=', '').str.replace('"', '').str.replace('-', '').str.strip()
            
            books_list = df.to_dict('records')
            books_list = [b for b in books_list if b.get('Identifier')]

        elif mode == 'text':
            title_col = next((col for col in df.columns if col.lower() == 'title' or col.lower() == 'titulo'), None)
            author_col = next((col for col in df.columns if col.lower() == 'author' or col.lower() == 'autor'), None)

            if not title_col or not author_col:
                print(f"Error: Columns 'Title' and 'Author' required for text mode not found in {file_path}")
                return []
            
            df = df.dropna(subset=[title_col, author_col])
            
            df = df.rename(columns={title_col: 'Title', author_col: 'Author'})
            
            books_list = df.to_dict('records')

        return books_list

    except Exception as e:
        print(f"Error: {e}")
        return []

def save_results(data, output_path):
    try:
        df = pd.DataFrame(data)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def _read_csv_any_encoding(file_path):
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(file_path, dtype=str, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {file_path} with any known encoding.")