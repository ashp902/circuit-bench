import { CheckCircleIcon, CircleIcon, XCircleIcon } from "@phosphor-icons/react/dist/ssr";

import { constraintText } from "@/lib/format";
import type { Challenge, ConstraintEvaluation } from "@/lib/types";

export function GoalPanel({ challenge, evaluation }: { challenge: Challenge; evaluation: ConstraintEvaluation | null }) {
  const resultById = new Map(evaluation?.results.map((result) => [result.constraint_id, result]));
  return (
    <aside className="goal-panel panel" aria-label="Challenge goal">
      <p className="section-kicker">Requirements</p>
      <h2>{challenge.title}</h2>
      <p className="panel-copy">{challenge.description}</p>
      <div className="constraint-list">
        {challenge.constraints.map((constraint) => {
          const result = resultById.get(constraint.id);
          const state = result?.status ?? "NOT_EVALUATED";
          const Icon = state === "PASS" ? CheckCircleIcon : state === "FAIL" ? XCircleIcon : CircleIcon;
          return <div className={`constraint constraint--${state.toLowerCase()}`} key={constraint.id} title={result?.message}>
            <Icon aria-hidden size={18} weight={state === "NOT_EVALUATED" ? "regular" : "fill"} />
            <span>{constraintText(constraint)}</span>
          </div>;
        })}
      </div>
      <div className="property-row"><span>Component limit</span><strong>{challenge.component_limit}</strong></div>
    </aside>
  );
}
