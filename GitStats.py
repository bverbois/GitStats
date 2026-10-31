import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import git
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta, timezone

class GitStats:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GitStats")
        self.root.geometry("1200x800")
        
        # Bind the window close event to explicitly kill the program
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        self.file_df = pd.DataFrame()
        self.excluded_extensions = set()
        self.current_canvas = None
        
        self._build_ui()

    def _on_closing(self):
        """Ensures the terminal process is interrupted when the window closes."""
        self.root.quit()
        self.root.destroy()
        sys.exit(0)

    def _build_ui(self):
        # Top Control Frame
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(control_frame, text="Repo Path:").pack(side=tk.LEFT, padx=5)
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(control_frame, textvariable=self.path_var, width=40)
        self.path_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(control_frame, text="Browse", command=self._browse_repo).pack(side=tk.LEFT, padx=5)

        ttk.Label(control_frame, text="Timeframe:").pack(side=tk.LEFT, padx=(20, 5))
        self.timeframe_var = tk.StringVar(value="Lifetime")
        self.timeframe_cb = ttk.Combobox(control_frame, textvariable=self.timeframe_var, 
                                         values=["Lifetime", "Past Month", "Past Week"], state="readonly", width=15)
        self.timeframe_cb.pack(side=tk.LEFT, padx=5)
        self.timeframe_cb.bind("<<ComboboxSelected>>", lambda e: self._update_graphs())

        self.filter_btn = ttk.Button(control_frame, text="Filter Filetypes", command=self._open_filter_dialog, state=tk.DISABLED)
        self.filter_btn.pack(side=tk.LEFT, padx=5)

        self.all_branches_var = tk.BooleanVar(value=False)
        self.all_branches_cb = ttk.Checkbutton(control_frame, text="All Branches", variable=self.all_branches_var)
        self.all_branches_cb.pack(side=tk.LEFT, padx=(15, 5))

        ttk.Button(control_frame, text="Analyze", command=self._analyze_repo).pack(side=tk.LEFT, padx=10)

        # Notebook for Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Graph Container
        self.graph_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.graph_frame, text="Metrics Dashboard")

    def _browse_repo(self):
        folder_selected = filedialog.askdirectory(title="GitStats")
        if folder_selected:
            self.path_var.set(folder_selected)

    def _open_filter_dialog(self):
        if self.file_df.empty:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Filter Filetypes")
        dialog.geometry("300x400")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Select filetypes to EXCLUDE:").pack(pady=10)

        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE, yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        unique_exts = sorted(self.file_df['extension'].unique())
        for idx, ext in enumerate(unique_exts):
            listbox.insert(tk.END, ext)
            if ext in self.excluded_extensions:
                listbox.selection_set(idx)

        def apply_filters():
            self.excluded_extensions = {listbox.get(i) for i in listbox.curselection()}
            self._update_graphs()
            dialog.destroy()

        ttk.Button(dialog, text="Apply Filters", command=apply_filters).pack(pady=10)

    def _analyze_repo(self):
        repo_path = self.path_var.get()
        if not repo_path:
            messagebox.showwarning("Input Error", "Please select a repository path.")
            return

        try:
            repo = git.Repo(repo_path)
            if repo.bare:
                raise git.exc.InvalidGitRepositoryError
        except git.exc.InvalidGitRepositoryError:
            messagebox.showerror("Error", "The selected folder is not a valid Git repository.")
            return

        file_data = []
        
        try:
            fetch_all = self.all_branches_var.get()
            
            for commit in repo.iter_commits(all=fetch_all):
                if len(commit.parents) > 1:
                    continue

                for filepath, file_stats in commit.stats.files.items():
                    ext = os.path.splitext(filepath)[1].lower()
                    if not ext:
                        ext = 'no extension'
                    
                    file_data.append({
                        'hash': commit.hexsha,
                        'author': commit.author.name,
                        'date': commit.committed_datetime,
                        'extension': ext,
                        'insertions': file_stats['insertions'],
                        'deletions': file_stats['deletions']
                    })
                    
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read commits: {e}")
            return

        if not file_data:
            messagebox.showinfo("Empty", "No valid commits/files found in this repository.")
            return

        self.file_df = pd.DataFrame(file_data)
        self.file_df['date'] = pd.to_datetime(self.file_df['date'], utc=True)
        
        self.excluded_extensions = set()
        self.filter_btn.config(state=tk.NORMAL)

        self._update_graphs()

    def _filter_data(self):
        if self.file_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        filtered_file_df = self.file_df.copy()

        timeframe = self.timeframe_var.get()
        now = datetime.now(timezone.utc)
        
        if timeframe == "Past Week":
            cutoff = now - timedelta(weeks=1)
            filtered_file_df = filtered_file_df[filtered_file_df['date'] >= cutoff]
        elif timeframe == "Past Month":
            cutoff = now - timedelta(days=30)
            filtered_file_df = filtered_file_df[filtered_file_df['date'] >= cutoff]

        if self.excluded_extensions:
            filtered_file_df = filtered_file_df[~filtered_file_df['extension'].isin(self.excluded_extensions)]

        if filtered_file_df.empty:
            return pd.DataFrame(), pd.DataFrame()

        commit_df = filtered_file_df.groupby(['hash', 'author', 'date']).agg({
            'insertions': 'sum',
            'deletions': 'sum'
        }).reset_index()
        
        commit_df = commit_df.sort_values(by='date', ascending=False).reset_index(drop=True)

        return commit_df, filtered_file_df

    def _update_graphs(self):
        filtered_commit_df, filtered_file_df = self._filter_data()
        
        if self.current_canvas:
            self.current_canvas.get_tk_widget().destroy()
            self.current_canvas = None

        if filtered_commit_df.empty:
            messagebox.showinfo("No Data", "No data available for the selected filters.")
            return

        fig, axs = plt.subplots(2, 3, figsize=(16, 9))
        fig.tight_layout(pad=5.0)

        # Extract the exact top 10 authors for consistency across all identity-based graphs/tables
        commits_per_author = filtered_commit_df['author'].value_counts()
        top_10_authors = commits_per_author.head(10)

        # 1. Commits per Identity (Top 10)
        axs[0, 0].bar(top_10_authors.index, top_10_authors.values, color='skyblue')
        axs[0, 0].set_title('Commits per Identity (Top 10)')
        axs[0, 0].set_ylabel('Number of Commits')
        axs[0, 0].tick_params(axis='x', rotation=90)

        # 2. Lines of Code (Additions/Deletions) per Identity (Top 10)
        loc_per_author = filtered_commit_df.groupby('author')[['insertions', 'deletions']].sum()
        loc_per_author = loc_per_author.reindex(top_10_authors.index) # Order by commit count to match graph 1
        loc_per_author.plot(kind='bar', stacked=True, ax=axs[0, 1], color=['#2ca02c', '#d62728'])
        axs[0, 1].set_title('Lines of Code per Identity (Top 10)')
        axs[0, 1].set_ylabel('Lines')
        axs[0, 1].tick_params(axis='x', rotation=90)

        # 3. Additions & Deletions per Commit
        axs[0, 2].scatter(filtered_commit_df.index, filtered_commit_df['insertions'], alpha=0.5, label='Additions', color='green')
        axs[0, 2].scatter(filtered_commit_df.index, filtered_commit_df['deletions'], alpha=0.5, label='Deletions', color='red')
        axs[0, 2].set_title('Additions vs Deletions per Commit')
        axs[0, 2].set_xlabel('Commit Index (Latest -> Oldest)')
        axs[0, 2].set_ylabel('Lines')
        axs[0, 2].legend()

        # 4. Activity Over Time
        filtered_commit_df['date_only'] = filtered_commit_df['date'].dt.date
        activity_over_time = filtered_commit_df.groupby('date_only').size()
        axs[1, 0].plot(activity_over_time.index, activity_over_time.values, marker='o', linestyle='-', color='purple')
        axs[1, 0].set_title('Commit Activity Over Time')
        axs[1, 0].set_ylabel('Commits')
        axs[1, 0].tick_params(axis='x', rotation=90)

        # 5. Lines of Code by Filetype (Top 10)
        loc_per_ext = filtered_file_df.groupby('extension')[['insertions', 'deletions']].sum()
        loc_per_ext['total'] = loc_per_ext['insertions'] + loc_per_ext['deletions']
        loc_per_ext = loc_per_ext.sort_values(by='total', ascending=False).head(10)
        
        loc_per_ext[['insertions', 'deletions']].plot(kind='bar', stacked=True, ax=axs[1, 1], color=['#2ca02c', '#d62728'])
        axs[1, 1].set_title('Top 10 Filetypes by Lines Changed')
        axs[1, 1].set_ylabel('Lines')
        axs[1, 1].tick_params(axis='x', rotation=90)

        # 6. Author Summary Table (Top 10)
        axs[1, 2].axis('off')
        axs[1, 2].set_title('Author Statistics (Top 10)', pad=10)

        author_loc_totals = filtered_commit_df.groupby('author')[['insertions', 'deletions']].sum()
        author_loc_totals['total'] = author_loc_totals['insertions']

        file_loc_calc = filtered_file_df.copy()
        file_loc_calc['total'] = file_loc_calc['insertions']
        
        ext_loc_grouped = file_loc_calc.groupby(['author', 'extension'])['total'].sum().reset_index()

        table_data = []
        for author in top_10_authors.index:
            commits = top_10_authors[author]
            total_loc = author_loc_totals.loc[author, 'total']
            
            author_exts = ext_loc_grouped[ext_loc_grouped['author'] == author].sort_values(by='total', ascending=False)
            ext_strings = [f"{row['extension']}({row['total']})" for _, row in author_exts.iterrows()]
            
            if len(ext_strings) > 3:
                ext_str = ", ".join(ext_strings[:3]) + ", etc."
            else:
                ext_str = ", ".join(ext_strings)
                
            table_data.append([author, commits, total_loc, ext_str])

        # FIX: Sort the compiled table data by Total LOC (index 2) descending
        table_data.sort(key=lambda row: row[2], reverse=True)

        columns = ["Identity", "Commits", "Total LOC", "LOC Breakdown"]
        
        if table_data:
            table = axs[1, 2].table(cellText=table_data, colLabels=columns, loc='center', cellLoc='center')
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1, 1.5)
            table.auto_set_column_width(col=list(range(len(columns))))

        # Embed in Tkinter
        self.current_canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
        self.current_canvas.draw()
        self.current_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    root = tk.Tk()
    app = GitStats(root)
    root.mainloop()