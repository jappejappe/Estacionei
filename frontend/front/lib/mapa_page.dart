import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

/// Tela principal do Estacionei — mapa de Concórdia - SC com busca e centralização.
class MapaPage extends StatefulWidget {
  const MapaPage({super.key});

  @override
  State<MapaPage> createState() => _MapaPageState();
}

class _MapaPageState extends State<MapaPage> {
  // Coordenadas fixas de Concórdia - SC (dados mock até integrar API/banco)
  static const double _latitude = -27.2342;
  static const double _longitude = -52.0270;
  static const double _zoomInicial = 14.0;

  /// Controla a câmera do mapa (zoom, pan e recentralização programática).
  final MapController _mapController = MapController();

  LatLng get _centroConcordia => const LatLng(_latitude, _longitude);

  /// Recentraliza o mapa nas coordenadas iniciais de Concórdia.
  void _centralizarMapa() {
    _mapController.move(_centroConcordia, _zoomInicial);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // Mapa em tela cheia; overlays ficam no Stack (sem AppBar).
      body: Stack(
        children: [
          _buildMapa(),
          _buildBarraDePesquisa(),
          _buildBotaoDashboard(),
          _buildBotaoCentralizar(),
        ],
      ),
    );
  }

  /// Camada base: FlutterMap com tiles OpenStreetMap ocupando 100% da tela.
  Widget _buildMapa() {
    return Positioned.fill(
      child: FlutterMap(
        mapController: _mapController,
        options: MapOptions(
          initialCenter: _centroConcordia,
          initialZoom: _zoomInicial,
        ),
        children: [
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.example.front',
          ),
        ],
      ),
    );
  }

  /// Barra de pesquisa flutuante no topo, abaixo da status bar.
  Widget _buildBarraDePesquisa() {
    final topoSeguro = MediaQuery.of(context).padding.top;

    return Positioned(
      top: topoSeguro + 8,
      left: 16,
      right: 16,
      child: Material(
        elevation: 4,
        borderRadius: BorderRadius.circular(12),
        color: Colors.white,
        child: TextField(
          decoration: InputDecoration(
            hintText: 'Buscar vagas de estacionamento...',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: IconButton(
              icon: const Icon(Icons.mic),
              onPressed: () {
                // Placeholder: reconhecimento de voz virá em versão futura.
              },
            ),
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide.none,
            ),
            contentPadding: const EdgeInsets.symmetric(vertical: 14),
          ),
        ),
      ),
    );
  }

  /// Botão flutuante no canto inferior esquerdo para abrir o painel de vagas.
  Widget _buildBotaoDashboard() {
    return Positioned(
      left: 16,
      bottom: 24,
      child: FloatingActionButton(
        heroTag: 'dashboard',
        onPressed: () => Navigator.pushNamed(context, '/dashboard'),
        tooltip: 'Painel de Vagas',
        backgroundColor: Colors.white,
        foregroundColor: const Color(0xFF000000),
        child: const Icon(Icons.dashboard),
      ),
    );
  }

  /// FAB no canto inferior direito para voltar ao centro de Concórdia.
  Widget _buildBotaoCentralizar() {
    return Positioned(
      right: 16,
      bottom: 24,
      child: FloatingActionButton(
        heroTag: 'centralizar',
        onPressed: _centralizarMapa,
        tooltip: 'Centralizar em Concórdia',
        child: const Icon(Icons.my_location),
      ),
    );
  }
}
