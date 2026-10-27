// Proposed standalone application DTOs. Import the existing VersionRef when integrating.
// This file does not replace generated algorithm contracts.
export type VersionRef = { id: string; version: string };
export type Module = 'routine' | 'forecast' | 'emergency' | 'packing';
export type CreateReview = {
  apiVersion: '1.0.0-draft'; datasetId: string; snapshotRef: VersionRef;
  runRef: VersionRef; planRef: VersionRef | null; configVersion: string;
  evidenceBundleRef: VersionRef; module: Module;
  reviewMode: 'result_review' | 'execution_review';
  purpose: 'retrospective_review' | 'decision_support';
  knowledgeCutoff: string; idempotencyKey: string;
};
export type ReviewJob = {
  apiVersion: '1.0.0-draft'; jobId: string; request: CreateReview;
  status: 'queued' | 'auditing' | 'retrieving' | 'analyzing' | 'completed' | 'failed';
  auditStatus: 'pending' | 'PASS' | 'FAIL' | 'NOT_CHECKED';
  llmStatus: 'not_configured' | 'pending' | 'succeeded' | 'failed' | 'skipped';
  report: null | {
    summary: string; deterministicChecks: Array<{name:string;status:'PASS'|'FAIL'|'NOT_CHECKED';evidenceIds:string[]}>;
    facts: Array<{text:string;evidenceIds:string[]}>;
    hypotheses: Array<{text:string;evidenceIds:string[]}>;
    suggestions: Array<{text:string;requiresValidation:boolean;evidenceIds:string[]}>;
    experienceRefs: VersionRef[]; limitations: string[];
    productionStateMutated: false;
  };
  error: null | {code:string;message:string};
};
export interface ReviewPort {
  create(input:CreateReview,signal?:AbortSignal):Promise<{jobId:string;status:'queued';statusUrl:string} | ReviewJob>;
  read(jobId:string,signal?:AbortSignal):Promise<ReviewJob>;
}
