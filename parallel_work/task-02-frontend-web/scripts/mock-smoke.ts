import { mockApi } from "../src/lib/api/mockApi";

async function main() {
  const session = await mockApi.login({
    username: "admin",
    password: "FaceReco2026!",
  });
  const [system, cameras, logs, attendance, faces] = await Promise.all([
    mockApi.getSystemStatus(),
    mockApi.getCameras(),
    mockApi.getLogs({}),
    mockApi.getAttendance({}),
    mockApi.getFaceLibrary(),
  ]);

  if (!session.token) {
    throw new Error("mock login did not return a token");
  }
  if (!cameras.length) {
    throw new Error("mock cameras are empty");
  }
  if (!logs.length) {
    throw new Error("mock logs are empty");
  }
  if (!attendance.length) {
    throw new Error("mock attendance is empty");
  }
  if (!faces.length) {
    throw new Error("mock face library is empty");
  }

  const startResult = await mockApi.startCamera(cameras[0].camera_id);
  const stopResult = await mockApi.stopCamera(cameras[0].camera_id);

  console.log(
    JSON.stringify(
      {
        login: session.user.name,
        system: system.overall,
        cameras: cameras.length,
        logs: logs.length,
        attendance: attendance.length,
        faces: faces.length,
        start: startResult.success,
        stop: stopResult.success,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
