"""FastAPI application for Voice Live Agent."""

import logging
import os
from uuid import uuid4
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.voicelive.session import VoiceLiveSession
from app.context.manager import ContextManager
from app.subagent.oob import OOBSubagent
from app.phases.router import PhaseRouter

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Voice Live Agent",
    description="Azure Voice Live API based call center agent",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "voice-live-agent"}


@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """WebSocket endpoint for voice communication."""
    await websocket.accept()
    call_id = str(uuid4())

    logger.info(f"New WebSocket connection: call_id={call_id}")

    # Initialize components
    voice_live_session = None
    context_manager = None

    try:
        # Create Voice Live session
        voice_live_session = VoiceLiveSession(frontend_ws=websocket)
        await voice_live_session.connect()

        # Create context manager
        context_manager = ContextManager(
            call_id=call_id,
            summary_threshold=settings.summary_token_threshold,
        )

        # Create OOB subagent
        oob_subagent = OOBSubagent(session=voice_live_session)

        # Create phase router
        phase_router = PhaseRouter(
            session=voice_live_session,
            context_manager=context_manager,
            oob_subagent=oob_subagent,
        )

        # Start Voice Live event handler
        import asyncio
        voice_live_task = asyncio.create_task(
            voice_live_session.handle_voice_live_events(
                phase_router=phase_router,
                context_manager=context_manager,
                oob_subagent=oob_subagent,
            )
        )

        # Handle frontend messages
        while True:
            try:
                message = await websocket.receive_json()
                msg_type = message.get("type", "")

                if msg_type == "audio":
                    # Forward audio to Voice Live
                    audio_data = message.get("data", "")
                    await voice_live_session.send_audio_to_voice_live(audio_data)

                elif msg_type == "control":
                    action = message.get("action", "")
                    if action == "start":
                        logger.info("Session started by client")
                    elif action == "stop":
                        logger.info("Session stopped by client")
                        break

            except Exception as e:
                logger.error(f"Error processing frontend message: {e}", exc_info=True)
                break

        # Cancel Voice Live task
        voice_live_task.cancel()
        try:
            await voice_live_task
        except asyncio.CancelledError:
            pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: call_id={call_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}", exc_info=True)
    finally:
        # Cleanup
        if voice_live_session:
            await voice_live_session.close()

        # Dump conversation log
        if context_manager:
            os.makedirs("./logs", exist_ok=True)
            log_path = f"./logs/call_{call_id}.json"
            context_manager.dump(log_path)
            logger.info(f"Session ended: call_id={call_id}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
