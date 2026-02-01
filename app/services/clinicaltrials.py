import requests
from typing import List, Optional
from dataclasses import dataclass
from urllib.parse import urlencode
import logging

logger = logging.getLogger("clinicaltrials-client")


@dataclass
class TrialHit:
    nct_id: str
    title: str
    phase: Optional[str]
    status: str
    sponsor: str
    conditions: List[str]
    locations_count: int
    url: str
    start_year: Optional[int] = None
    score: float = 0.0


class ClinicalTrialsError(Exception):
    pass


class ClinicalTrialsClient:
    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    def search_studies(self, term: str, limit: int = 20) -> List[TrialHit]:
        if not term.strip():
            return []

        params = {
            "query.term": term,
            "pageSize": limit
        }

        url = f"{self.BASE_URL}?{urlencode(params)}"
        logger.info("ClinicalTrials.gov query → %s", term)

        resp = requests.get(
            url,
            timeout=15,
            headers={
                "Accept": "application/json",
                "User-Agent": "NovusAI/1.0"
            }
        )

        if resp.status_code == 400:
            return []

        if resp.status_code != 200:
            raise ClinicalTrialsError(f"HTTP {resp.status_code}")

        studies = resp.json().get("studies", [])
        return self._parse_studies(studies)

    def _parse_studies(self, studies: list) -> List[TrialHit]:
        trials: List[TrialHit] = []

        for s in studies:
            proto = s.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status = proto.get("statusModule", {})
            sponsor = proto.get("sponsorCollaboratorsModule", {})
            cond = proto.get("conditionsModule", {})
            design = proto.get("designModule", {})
            loc = proto.get("contactsLocationsModule", {})

            nct = ident.get("nctId")
            if not nct:
                continue

            start_year = (
                status.get("startDateStruct", {}) or {}
            ).get("year")

            phases = design.get("phases") or []

            trials.append(
                TrialHit(
                    nct_id=nct,
                    title=ident.get("briefTitle", ""),
                    phase=phases[0] if phases else None,
                    status=status.get("overallStatus", "Unknown"),
                    sponsor=sponsor.get("leadSponsor", {}).get("name", "Unknown"),
                    conditions=cond.get("conditions", []),
                    locations_count=len(loc.get("locations", [])),
                    url=f"https://clinicaltrials.gov/study/{nct}",
                    start_year=start_year
                )
            )

        return trials


client = ClinicalTrialsClient()
