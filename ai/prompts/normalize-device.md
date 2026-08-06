You are cleaning up messy network device fields discovered via CDP/LLDP.

Given:
- raw hostname: {raw_hostname}
- raw platform string: {raw_platform}

Return ONLY a JSON object with exactly these keys, no other text:
{{
  "hostname": "<cleaned short hostname, lowercase, no trailing domain suffix>",
  "manufacturer": "<vendor name, e.g. Cisco>",
  "model": "<model number only, without vendor prefix>",
  "confidence": <float 0.0-1.0 indicating how confident you are>
}}
