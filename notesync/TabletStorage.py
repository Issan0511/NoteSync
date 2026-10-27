"""One-time browser preference copy when upgrading from the former app name."""
STORAGE_SCRIPT = r"""
(function migrateNotebookPreferences(){
  try {
    for(const suffix of ['favorite_pens','current_pen','brush_settings','eraser_mode','pen_button_mode','library_view','library_sort']){
      const target='notesync_'+suffix, source='beamerplus_'+suffix;
      if(localStorage.getItem(target)===null){
        const value=localStorage.getItem(source);
        if(value!==null)localStorage.setItem(target,value);
      }
    }
  } catch(_){} // Private browsers can reject storage; editing must still work.
})();
"""
