# Nikosh

AI-powered recruitment and interview intelligence platform (BJIT Academy final project).

## Run

```bash
docker compose up -d --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs

Rebuild with the same command after code changes. Backend logs:
`docker compose logs backend --tail 30`.

## Demo setup (video interview)

The camera and microphone only work on `localhost` or HTTPS.

### Single PC

1. Open http://localhost:3000.
2. Interviewer: log in with **Chrome** (normal window).
3. Candidate: open the join link from the invitation email in **Edge**.
4. Give each browser its own microphone (pick it on the device check
   screen) and use headphones to avoid echo.
5. With only one webcam, the second browser cannot open it. The candidate
   then joins with the microphone only and still sees the interviewer's
   video.

### Two PCs (Cloudflare quick tunnel)

PC 1 runs the system; PC 2 only needs a browser.

1. On PC 1, install
   [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
   (no account needed).
2. Start the system, then the tunnel:

   ```bash
   cloudflared tunnel --url http://localhost:3000
   ```

   Copy the printed `https://<random>.trycloudflare.com` URL. It changes
   every time the tunnel starts.
3. In `backend/.env` set `FRONTEND_BASE_URL=https://<random>.trycloudflare.com`.
4. Recreate the backend so it reads the new value (`restart` does not
   reload `.env`):

   ```bash
   docker compose up -d backend
   ```

5. Schedule the interview (or use "Resend invitation") **after** this
   step, so the email contains the tunnel link.
6. Interviewer on PC 1: http://localhost:3000 (or the tunnel URL).
   Candidate on PC 2: open the link from the email.
7. Afterwards, stop the tunnel, set
   `FRONTEND_BASE_URL=http://localhost:3000` again and run
   `docker compose up -d backend`.

If a strict network (e.g. office firewall) blocks the call after
"Connecting...", add a TURN server in a root `.env` file and rebuild the
frontend:

```bash
VITE_ICE_SERVERS=[{"urls":"stun:stun.l.google.com:19302"},{"urls":"turn:<host>:3478","username":"<user>","credential":"<password>"}]
```

```bash
docker compose up -d --build frontend
```
