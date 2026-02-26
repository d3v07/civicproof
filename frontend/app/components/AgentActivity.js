'use client';

import { useState, useEffect } from 'react';

// Agent definitions for the CivicProof investigative pipeline
const AGENTS = {
    'data-engineer': {
        name: 'Data Engineer',
        initials: 'DE',
        color: '#2378c3',
        description: 'Fetches and normalizes data from federal sources',
    },
    'entity-resolver': {
        name: 'Entity Resolver',
        initials: 'ER',
        color: '#216e1f',
        description: 'Links and disambiguates entities across datasets',
    },
    'evidence-retriever': {
        name: 'Evidence Retriever',
        initials: 'EV',
        color: '#c2850c',
        description: 'Retrieves supporting artifacts for claims',
    },
    'claim-composer': {
        name: 'Claim Composer',
        initials: 'CC',
        color: '#8b6b00',
        description: 'Constructs grounded claims from evidence',
    },
    'graph-builder': {
        name: 'Graph Builder',
        initials: 'GB',
        color: '#6b21a8',
        description: 'Constructs relationship graph between entities',
    },
    'auditor': {
        name: 'AI Auditor',
        initials: 'AU',
        color: '#b50d12',
        description: 'Reviews claims for hallucinations and unsupported assertions',
    },
};

// Simulated agent activity messages per pipeline stage
const STAGE_MESSAGES = {
    'data-engineer': [
        'Querying USAspending API for contract awards...',
        'Fetching SAM.gov entity registration records...',
        'Pulling FPDS procurement data...',
        'Normalizing SEC EDGAR filings...',
        'Content-hashing 12 retrieved artifacts...',
        'Indexing DOJ press releases for entity mentions...',
    ],
    'entity-resolver': [
        'Resolving UEI across 3 data sources...',
        'Matching CAGE codes to SAM.gov registrations...',
        'Disambiguating subsidiary relationships...',
        'Linking officer names to entity graph...',
    ],
    'evidence-retriever': [
        'Retrieving contract documents from USAspending...',
        'Fetching supporting financial disclosures...',
        'Cross-referencing award amounts with budget data...',
    ],
    'claim-composer': [
        'Composing sole-source pattern hypothesis...',
        'Generating risk signal from award concentration...',
        'Citing evidence artifacts for each claim...',
    ],
    'graph-builder': [
        'Constructing entity relationship graph...',
        'Calculating centrality scores for key entities...',
        'Mapping contract award flow paths...',
    ],
    'auditor': [
        'Reviewing claims for unsupported assertions...',
        'Verifying citation coverage on all findings...',
        'Checking for hallucinated entity relationships...',
        'Validating provenance chain integrity...',
    ],
};

function AgentAvatar({ agentKey, size = 28 }) {
    const agent = AGENTS[agentKey];
    if (!agent) return null;
    return (
        <span
            className="agent-avatar"
            style={{
                width: size,
                height: size,
                backgroundColor: agent.color,
                fontSize: size * 0.39,
            }}
            title={agent.name}
            aria-label={agent.name}
        >
            {agent.initials}
        </span>
    );
}

function ThinkingDots() {
    return (
        <span className="thinking-dots" aria-label="Agent is processing">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
        </span>
    );
}

// Mini inline agent progress for case rows on homepage
export function AgentProgressInline({ caseId }) {
    const [activity, setActivity] = useState(null);

    useEffect(() => {
        // Simulate cycling through agent activities
        const agentKeys = Object.keys(AGENTS);
        let idx = 0;

        const cycleAgent = () => {
            const agentKey = agentKeys[idx % agentKeys.length];
            const messages = STAGE_MESSAGES[agentKey];
            const msg = messages[Math.floor(Math.random() * messages.length)];
            setActivity({ agentKey, message: msg });
            idx++;
        };

        cycleAgent();
        const interval = setInterval(cycleAgent, 4000);
        return () => clearInterval(interval);
    }, [caseId]);

    if (!activity) return null;

    return (
        <div className="agent-inline">
            <AgentAvatar agentKey={activity.agentKey} size={20} />
            <span className="agent-inline-text">{activity.message}</span>
            <ThinkingDots />
        </div>
    );
}

// Full agent activity feed (for case detail or standalone)
export default function AgentActivity({ events, isLive = false }) {
    // If no events provided, use simulated feed
    const [feed, setFeed] = useState(events || []);

    useEffect(() => {
        if (events) {
            setFeed(events);
            return;
        }

        // Simulate a live feed
        const agentKeys = Object.keys(AGENTS);
        const initialFeed = agentKeys.slice(0, 3).map((key, i) => {
            const msgs = STAGE_MESSAGES[key];
            return {
                id: `evt-${i}`,
                agent: key,
                message: msgs[Math.floor(Math.random() * msgs.length)],
                timestamp: new Date(Date.now() - (3 - i) * 12000).toISOString(),
                status: i < 2 ? 'complete' : 'active',
            };
        });
        setFeed(initialFeed);
    }, [events]);

    return (
        <div className="agent-feed" role="log" aria-label="Agent activity">
            {feed.map((event) => {
                const agent = AGENTS[event.agent];
                if (!agent) return null;
                return (
                    <div key={event.id} className={`agent-feed-entry ${event.status === 'active' ? 'agent-feed-active' : ''}`}>
                        <AgentAvatar agentKey={event.agent} />
                        <div className="agent-feed-content">
                            <div className="agent-feed-header">
                                <span className="agent-feed-name">{agent.name}</span>
                                <span className="agent-feed-time">
                                    {new Date(event.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
                                </span>
                            </div>
                            <div className="agent-feed-message">
                                {event.message}
                                {event.status === 'active' && <ThinkingDots />}
                            </div>
                        </div>
                        {event.status === 'complete' && (
                            <span className="agent-feed-check" aria-label="Complete">✓</span>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

export { AGENTS, AgentAvatar, ThinkingDots };
