// Complete implementation of condition-based waiting utilities
// From: Lace test infrastructure improvements (2025-10-03)
// Context: Fixed 15 flaky tests by replacing arbitrary timeouts
// Note: Uses generic, self-contained types — adapt EventType values to your domain

// ---------------------------------------------------------------------------
// Generic domain types (inline — no external imports required)
// ---------------------------------------------------------------------------

export type EventType = string;

export interface Event {
  type: EventType;
  data?: unknown;
  timestamp?: number;
}

export interface EventManager {
  getEvents(channelId: string): Event[];
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Wait for a specific event type to appear in a channel
 *
 * @param manager - The event manager to query
 * @param channelId - Channel to check for events
 * @param eventType - Type of event to wait for
 * @param timeoutMs - Maximum time to wait (default 5000ms)
 * @returns Promise resolving to the first matching event
 *
 * Example:
 *   await waitForEvent(manager, agentChannelId, 'TOOL_RESULT');
 */
export function waitForEvent(
  manager: EventManager,
  channelId: string,
  eventType: EventType,
  timeoutMs = 5000
): Promise<Event> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();

    const check = () => {
      const events = manager.getEvents(channelId);
      const event = events.find((e) => e.type === eventType);

      if (event) {
        resolve(event);
      } else if (Date.now() - startTime > timeoutMs) {
        reject(new Error(`Timeout waiting for ${eventType} event after ${timeoutMs}ms`));
      } else {
        setTimeout(check, 10); // Poll every 10ms for efficiency
      }
    };

    check();
  });
}

/**
 * Wait for a specific number of events of a given type
 *
 * @param manager - The event manager to query
 * @param channelId - Channel to check for events
 * @param eventType - Type of event to wait for
 * @param count - Number of events to wait for
 * @param timeoutMs - Maximum time to wait (default 5000ms)
 * @returns Promise resolving to all matching events once count is reached
 *
 * Example:
 *   // Wait for 2 AGENT_MESSAGE events (initial response + continuation)
 *   await waitForEventCount(manager, agentChannelId, 'AGENT_MESSAGE', 2);
 */
export function waitForEventCount(
  manager: EventManager,
  channelId: string,
  eventType: EventType,
  count: number,
  timeoutMs = 5000
): Promise<Event[]> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();

    const check = () => {
      const events = manager.getEvents(channelId);
      const matchingEvents = events.filter((e) => e.type === eventType);

      if (matchingEvents.length >= count) {
        resolve(matchingEvents);
      } else if (Date.now() - startTime > timeoutMs) {
        reject(
          new Error(
            `Timeout waiting for ${count} ${eventType} events after ${timeoutMs}ms (got ${matchingEvents.length})`
          )
        );
      } else {
        setTimeout(check, 10);
      }
    };

    check();
  });
}

/**
 * Wait for an event matching a custom predicate
 * Useful when you need to check event data, not just type
 *
 * @param manager - The event manager to query
 * @param channelId - Channel to check for events
 * @param predicate - Function that returns true when event matches
 * @param description - Human-readable description for error messages
 * @param timeoutMs - Maximum time to wait (default 5000ms)
 * @returns Promise resolving to the first matching event
 *
 * Example:
 *   // Wait for TOOL_RESULT with specific ID
 *   await waitForEventMatch(
 *     manager,
 *     agentChannelId,
 *     (e) => e.type === 'TOOL_RESULT' && (e.data as any)?.id === 'call_123',
 *     'TOOL_RESULT with id=call_123'
 *   );
 */
export function waitForEventMatch(
  manager: EventManager,
  channelId: string,
  predicate: (event: Event) => boolean,
  description: string,
  timeoutMs = 5000
): Promise<Event> {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();

    const check = () => {
      const events = manager.getEvents(channelId);
      const event = events.find(predicate);

      if (event) {
        resolve(event);
      } else if (Date.now() - startTime > timeoutMs) {
        reject(new Error(`Timeout waiting for ${description} after ${timeoutMs}ms`));
      } else {
        setTimeout(check, 10);
      }
    };

    check();
  });
}

// Usage example from actual debugging session:
//
// BEFORE (flaky):
// ---------------
// const messagePromise = agent.sendMessage('Execute tools');
// await new Promise(r => setTimeout(r, 300)); // Hope tools start in 300ms
// agent.abort();
// await messagePromise;
// await new Promise(r => setTimeout(r, 50));  // Hope results arrive in 50ms
// expect(toolResults.length).toBe(2);         // Fails randomly
//
// AFTER (reliable):
// ----------------
// const messagePromise = agent.sendMessage('Execute tools');
// await waitForEventCount(manager, channelId, 'TOOL_CALL', 2); // Wait for tools to start
// agent.abort();
// await messagePromise;
// await waitForEventCount(manager, channelId, 'TOOL_RESULT', 2); // Wait for results
// expect(toolResults.length).toBe(2); // Always succeeds
//
// Result: 60% pass rate → 100%, 40% faster execution
