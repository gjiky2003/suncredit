# SunCredit — First 10 Loans Operations Guide

## Goal
Prove the platform works in production and generate investor-grade loss curve data.

## Budget
| Item | Cost |
|------|------|
| Texas license + bond | $5k-8k |
| Capital pool | $15k-25k |
| Legal counsel | $3k-8k |
| Tooling (KYC, hosting, domain) | $200-500/mo |
| **Total** | **$23k-48k initial** |

## Borrower Sourcing
Don't compete with SoFi for top-tier borrowers in pilot. Focus on:

### Approach 1: Friends & Family (5 loans)
- Trusted contacts who actually need a loan
- $1k-$5k loans at 12-15% APR (your Tier A pricing)
- 12-24 month terms
- Risk: low (they won't default; protects pilot)

### Approach 2: Network of Network (3-5 loans)
- "Friends of friends" referrals via social network
- Slightly stricter underwriting
- $2k-$10k loans
- Real test of automation

### Approach 3: LinkedIn / Twitter Outreach (last 2-3 loans)
- Once first 7 loans are live without issues
- Target gig workers, immigrants, thin-file
- Validate cash flow underwriting
- These are your "investor demo" loans

## What to Track Per Loan
1. **Origination data:**
   - Application timestamp, time to decision (<1 min target)
   - Risk score, tier, APR offered
   - Cash flow score (if connected)
   - Approved/declined + reasons

2. **Servicing:**
   - Payment due dates and actual payment dates
   - Days past due (target: 0)
   - Collection actions taken

3. **Outcome:**
   - Status (active / paid_off / charged_off)
   - Total interest paid
   - Realized loss (if any)

## Success Metrics (after 10 loans)
- Origination automation: 100% (no manual intervention needed)
- Average time to fund: <24 hours
- Default rate: <10% (vs 5-8% expected)
- AUC validation: actual defaults align with predicted risk tiers

## When to Scale
After 10 loans + 60 days of payment history:
- If 0-1 defaults → raise debt facility, scale to 50 loans
- If 2-3 defaults → tune underwriting, add 10 more pilot loans
- If 4+ defaults → pause and analyze; underwriting needs work
