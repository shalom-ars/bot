const http = require('http');
const net = require('net');

const TARGET_HOST = '127.0.0.1';
const TARGET_PORT = 8000;

const server = http.createServer((req, res) => {
  const options = {
    hostname: TARGET_HOST,
    port: TARGET_PORT,
    path: req.url,
    method: req.method,
    headers: {
      ...req.headers,
      host: `${TARGET_HOST}:${TARGET_PORT}`,
      'x-forwarded-for': req.socket.remoteAddress,
      'x-forwarded-proto': 'http',
    },
  };

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on('error', (err) => {
    console.error('Proxy error:', err.message);
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'text/plain' });
      res.end('Bad Gateway');
    }
  });

  req.pipe(proxyReq, { end: true });
});

server.on('upgrade', (req, socket, head) => {
  const proxySocket = net.connect(TARGET_PORT, TARGET_HOST, () => {
    const headerLines = Object.keys(req.headers)
      .map((key) => `${key}: ${req.headers[key]}`)
      .join('\r\n');
    proxySocket.write(
      `${req.method} ${req.url} HTTP/1.1\r\n` +
      headerLines +
      '\r\n\r\n'
    );
    if (head && head.length > 0) proxySocket.write(head);
    socket.pipe(proxySocket);
    proxySocket.pipe(socket);
  });

  proxySocket.on('error', (err) => {
    console.error('WS Proxy error:', err.message);
    socket.destroy();
  });
});

server.listen(3000, '0.0.0.0', () => {
  console.log('Port 3000 proxy server listening and forwarding to 127.0.0.1:8000');
});
