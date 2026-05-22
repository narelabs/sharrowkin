from cognition.fieldscript.engine import FieldScript
import torch

def run_cognitive_cycle():
    print("\n" + "="*50)
    print(" FIELD AGENT COGNITIVE CYCLE — START")
    print("="*50)
    
    agent = FieldScript(dim=256)
    
    new_concept = "NARE-Field provides intelligence-per-token maximization."
    agent.observe(new_concept)
    
    agent.reason(depth=12)
    
    agent.recall("intelligence efficiency metrics")
    
    agent.stabilize()
    
    agent.commit("IpT Maximization is a core Field property.")
    
    print("="*50)
    print(" CYCLE COMPLETE. FIELD IS HARMONIOUS.")
    print("="*50 + "\n")

if __name__ == "__main__":
    with torch.no_grad():
        run_cognitive_cycle()
