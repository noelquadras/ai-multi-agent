try:
    from winpty import PtyProcess
    print("pywinpty installed successfully")
except ImportError as e:
    print(f"Error importing pywinpty: {e}")
