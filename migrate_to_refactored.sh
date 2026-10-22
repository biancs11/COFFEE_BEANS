#!/bin/bash
# Migration script: Switch to refactored camera architecture

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║  Camera Architecture Migration                        ║"
echo "║  Producer-Consumer for Real-Time Stream               ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo

# Step 1: Backup current implementation
echo "📦 Step 1: Backing up current implementation..."
cd ~/COFFEE_BEANS

if [ ! -f backend/core/camera_original.py ]; then
    cp backend/core/camera.py backend/core/camera_original.py
    echo "   ✓ Backed up camera.py → camera_original.py"
fi

if [ ! -f backend/api/websocket_original.py ]; then
    cp backend/api/websocket.py backend/api/websocket_original.py
    echo "   ✓ Backed up websocket.py → websocket_original.py"
fi

# Step 2: Test refactored camera (optional - requires X display)
echo
echo "🧪 Step 2: Testing refactored camera..."
echo "   Run this manually if you have a display:"
echo "     python3 test_camera_refactored.py"
echo "   Press any key to continue..."
read -n 1 -s

# Step 3: Swap implementations
echo
echo "🔄 Step 3: Swapping to refactored implementation..."

# Rename current to _old
mv backend/core/camera.py backend/core/camera_old.py
mv backend/api/websocket.py backend/api/websocket_old.py

# Rename refactored to current
mv backend/core/camera_refactored.py backend/core/camera.py
mv backend/api/websocket_refactored.py backend/api/websocket.py

echo "   ✓ Swapped camera.py"
echo "   ✓ Swapped websocket.py"

# Step 4: Update imports
echo
echo "📝 Step 4: Updating imports..."

# Update camera manager import
sed -i 's/from \.camera import camera_manager$/from .camera import camera_manager_refactored as camera_manager/' backend/core/__init__.py 2>/dev/null || true

echo "   ✓ Updated backend/core/__init__.py"

# Step 5: Restart system
echo
echo "🔄 Step 5: Restarting system..."
pkill -f "uvicorn backend.main" 2>/dev/null || true
sleep 2

bash start_system.sh &
SYSTEM_PID=$!

echo "   ✓ System restarted (PID: $SYSTEM_PID)"

# Step 6: Wait for startup
echo
echo "⏳ Step 6: Waiting for system startup (10s)..."
sleep 10

# Step 7: Check logs
echo
echo "📋 Step 7: Checking logs..."
if [ -f logs/backend.log ]; then
    echo "   Last 20 lines of backend.log:"
    tail -n 20 logs/backend.log
else
    echo "   ⚠ No log file found"
fi

# Step 8: Verification checklist
echo
echo "╔═══════════════════════════════════════════════════════╗"
echo "║  Migration Complete!                                  ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo
echo "✅ Verification Checklist:"
echo "   [ ] Open dashboard: http://$(hostname -I | awk '{print $1}'):8000"
echo "   [ ] Video stream is smooth (no lag)"
echo "   [ ] Beans are sharp (in focus)"
echo "   [ ] Colours are accurate (no blue/gold artifacts)"
echo "   [ ] Detection still works"
echo "   [ ] Check camera FPS in stats (should be ~30fps)"
echo
echo "🔙 Rollback (if needed):"
echo "   cd ~/COFFEE_BEANS"
echo "   bash rollback_camera.sh"
echo

# Create rollback script
cat > rollback_camera.sh << 'ROLLBACK'
#!/bin/bash
# Rollback to original camera implementation

echo "Rolling back to original camera..."
cd ~/COFFEE_BEANS

mv backend/core/camera.py backend/core/camera_refactored.py
mv backend/core/camera_old.py backend/core/camera.py

mv backend/api/websocket.py backend/api/websocket_refactored.py
mv backend/api/websocket_old.py backend/api/websocket.py

# Restore original import
sed -i 's/from \.camera import camera_manager_refactored as camera_manager$/from .camera import camera_manager/' backend/core/__init__.py 2>/dev/null || true

pkill -f "uvicorn backend.main" 2>/dev/null || true
sleep 2
bash start_system.sh

echo "✓ Rolled back to original implementation"
ROLLBACK

chmod +x rollback_camera.sh

echo "📄 Created rollback_camera.sh for easy rollback"
echo
echo "Done! Check the dashboard now."
