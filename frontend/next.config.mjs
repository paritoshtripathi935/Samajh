/** @type {import('next').NextConfig} */
const nextConfig = {
  // Sarvam Document-Intelligence outputs (digitised Markdown/JSON) can be
  // large; give server actions/route handlers room to stream them back.
  experimental: {
    serverActions: {
      bodySizeLimit: "50mb", // Sarvam DI accepts files up to 50 MB
    },
  },
};

export default nextConfig;
