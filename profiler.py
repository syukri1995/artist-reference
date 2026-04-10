import cProfile
import pstats
import io
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import Application

def run_profiler():
    print("Starting Artist Reference Manager under cProfile...")
    pr = cProfile.Profile()
    pr.enable()
    
    app = Application()
    app.mainloop()
    
    pr.disable()
    print("Application closed. Generating profile statistics...")
    
    s = io.StringIO()
    # Sort by cumulative time to see which high-level functions take the longest
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30) # Top 30 offenders
    
    with open("profile_results.txt", "w") as f:
        f.write(s.getvalue())
        
    print("Profile saved to profile_results.txt")

if __name__ == "__main__":
    run_profiler()
