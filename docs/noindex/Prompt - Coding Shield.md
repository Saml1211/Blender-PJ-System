### Prompt:
Before implementing any changes in my application, I'll complete this thorough preparation assessment:
```
{
  "change_specification": "What precisely needs to be changed or added?",
  
  "complete_understanding": {
    "affected_components": "Which specific parts of the codebase will this change affect?",
    "dependencies": "What dependencies exist between these components and other parts of the system?",
    "data_flow_impact": "How will this change affect the flow of data in the application?",
    "user_experience_impact": "How will this change affect the user interface and experience?"
  },
  
  "readiness_verification": {
    "required_knowledge": "Do I fully understand all technologies involved in this change?",
    "documentation_review": "Have I reviewed all relevant documentation for the components involved?",
    "similar_precedents": "Are there examples of similar changes I can reference?",
    "knowledge_gaps": "What aspects am I uncertain about, and how will I address these gaps?"
  },
  
  "risk_assessment": {
    "potential_failures": "What could go wrong with this implementation?",
    "cascading_effects": "What other parts of the system might break as a result of this change?",
    "performance_impacts": "Could this change affect application performance?",
    "security_implications": "Are there any security risks associated with this change?",
    "data_integrity_risks": "Could this change corrupt or compromise existing data?"
  },
  
  "mitigation_plan": {
    "testing_strategy": "How will I test this change before fully implementing it?",
    "rollback_procedure": "What is my step-by-step plan to revert these changes if needed?",
    "backup_approach": "How will I back up the current state before making changes?",
    "incremental_implementation": "Can this change be broken into smaller, safer steps?",
    "verification_checkpoints": "What specific checks will confirm successful implementation?"
  },
  
  "implementation_plan": {
    "isolated_development": "How will I develop this change without affecting the live system?",
    "precise_change_scope": "What exact files and functions will be modified?",
    "sequence_of_changes": "In what order will I make these modifications?",
    "validation_steps": "What tests will I run after each step?",
    "final_verification": "How will I comprehensively verify the completed change?"
  },
  
  "readiness_assessment": "Based on all the above, am I 100% ready to proceed safely?"
}
```
---

**⚠️ Tip:** If the final readiness assessment shows less than 100% ready, prompt with:

"Do what you must to be 100% ready and then go ahead."