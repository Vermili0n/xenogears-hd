#include "xeno_core.h"
#include "xeno_discs.h"

#include "../third_party/bc7decomp/bc7decomp.h"

#include <godot_cpp/classes/file_access.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/packed_color_array.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_vector2_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/vector4.hpp>

#include <cstring>

namespace godot
{
	namespace
	{
		String ToGodot(const std::string& Text)
		{
			return String::utf8(Text.c_str());
		}

		PackedFloat32Array Floats(const std::vector<float>& From)
		{
			PackedFloat32Array Out;
			Out.resize(static_cast<int64_t>(From.size()));
			if (!From.empty())
			{
				std::memcpy(Out.ptrw(), From.data(), From.size() * sizeof(float));
			}
			return Out;
		}

		void AddSurface(ArrayMesh& Mesh, const Xeno::FMeshBuffers& Buffers)
		{
			const int64_t Count = static_cast<int64_t>(Buffers.Vertices());
			PackedVector3Array Positions;
			Positions.resize(Count);
			PackedColorArray Colors;
			Colors.resize(Count);
			PackedVector2Array Uvs;
			Uvs.resize(Count);
			PackedVector3Array Normals;
			Normals.resize(Count);
			for (int64_t Vertex = 0; Vertex < Count; ++Vertex)
			{
				const float* P = &Buffers.Pos[static_cast<std::size_t>(Vertex) * 3];
				const float* C = &Buffers.Color[static_cast<std::size_t>(Vertex) * 4];
				const float* T = &Buffers.Uv[static_cast<std::size_t>(Vertex) * 2];
				const float* N = &Buffers.Normal[static_cast<std::size_t>(Vertex) * 3];
				Normals.set(Vertex, Vector3(N[0], N[1], N[2]));
				Positions.set(Vertex, Vector3(P[0], P[1], P[2]));
				Colors.set(Vertex, Color(C[0], C[1], C[2], C[3]));
				Uvs.set(Vertex, Vector2(T[0], T[1]));
			}
			Array Arrays;
			Arrays.resize(Mesh::ARRAY_MAX);
			Arrays[Mesh::ARRAY_VERTEX] = Positions;
			Arrays[Mesh::ARRAY_NORMAL] = Normals;
			Arrays[Mesh::ARRAY_COLOR] = Colors;
			Arrays[Mesh::ARRAY_TEX_UV] = Uvs;
			Arrays[Mesh::ARRAY_CUSTOM0] = Floats(Buffers.C0);
			Arrays[Mesh::ARRAY_CUSTOM1] = Floats(Buffers.C1);
			Arrays[Mesh::ARRAY_CUSTOM2] = Floats(Buffers.C2);
			Arrays[Mesh::ARRAY_CUSTOM3] = Floats(Buffers.C3);
			const BitField<Mesh::ArrayFormat> Format = (Mesh::ARRAY_CUSTOM_RGBA_FLOAT << Mesh::ARRAY_FORMAT_CUSTOM0_SHIFT)
				| (Mesh::ARRAY_CUSTOM_RGBA_FLOAT << Mesh::ARRAY_FORMAT_CUSTOM1_SHIFT) | (Mesh::ARRAY_CUSTOM_RGBA_FLOAT << Mesh::ARRAY_FORMAT_CUSTOM2_SHIFT)
				| (Mesh::ARRAY_CUSTOM_RGBA_FLOAT << Mesh::ARRAY_FORMAT_CUSTOM3_SHIFT);
			Mesh.add_surface_from_arrays(Mesh::PRIMITIVE_TRIANGLES, Arrays, Array(), Dictionary(), Format);
		}
	}

	namespace
	{
		/** A pack picture: XBC7 (32-byte header: magic, 0, width, height, 0, 0, raw size, flags; bit 0 zlib) level 0, or PNG. */
		bool ReadPicture(const std::string& Path, std::vector<uint8_t>& Rgba, int& Width, int& Height)
		{
			const PackedByteArray Bytes = FileAccess::get_file_as_bytes(String::utf8(Path.c_str()));
			if (Bytes.size() >= 32 && Bytes[0] == 'X' && Bytes[1] == 'B' && Bytes[2] == 'C' && Bytes[3] == '7')
			{
				Width = static_cast<int>(Bytes.decode_u32(8));
				Height = static_cast<int>(Bytes.decode_u32(12));
				const int64_t RawSize = Bytes.decode_u32(24);
				const bool bZlib = (Bytes.decode_u32(28) & 1) != 0;
				const PackedByteArray Raw = bZlib ? Bytes.slice(32).decompress(RawSize, FileAccess::COMPRESSION_DEFLATE) : Bytes.slice(32);
				const int BlocksWide = (Width + 3) / 4, BlocksHigh = (Height + 3) / 4;
				if (Raw.size() < static_cast<int64_t>(BlocksWide) * BlocksHigh * 16)
				{
					return false;
				}
				Rgba.assign(static_cast<std::size_t>(Width) * Height * 4, 0);
				bc7decomp::color_rgba Block[16];
				for (int By = 0; By < BlocksHigh; ++By)
				{
					for (int Bx = 0; Bx < BlocksWide; ++Bx)
					{
						bc7decomp::unpack_bc7(Raw.ptr() + (static_cast<std::size_t>(By) * BlocksWide + Bx) * 16, Block);
						for (int Texel = 0; Texel < 16; ++Texel)
						{
							const int X = Bx * 4 + (Texel & 3), Y = By * 4 + (Texel >> 2);
							if (X < Width && Y < Height)
							{
								std::memcpy(&Rgba[(static_cast<std::size_t>(Y) * Width + X) * 4], Block[Texel].m_comps, 4);
							}
						}
					}
				}
				return true;
			}
			Ref<Image> Png;
			Png.instantiate();
			if (Bytes.is_empty() || Png->load_png_from_buffer(Bytes) != OK)
			{
				return false;
			}
			Png->convert(Image::FORMAT_RGBA8);
			Width = Png->get_width();
			Height = Png->get_height();
			const PackedByteArray Data = Png->get_data();
			Rgba.assign(Data.ptr(), Data.ptr() + Data.size());
			return true;
		}

		/**
		 * A run of the 2D layer as a canvas mesh: 2D vertices in screen pixels, COLOR, UV, and the two attributes a
		 * canvas_item shader has. CUSTOM0 packs C0 and C1 as whole numbers a float holds exactly (below 2^24):
		 * (page x + 1024 * page y, clut x + 1024 * clut y, depth + 8 * flags, spans the display); CUSTOM1 is C2.
		 * The drawing area (C3) is the run's own (FSurface::Area), a uniform.
		 */
		void AddFlatSurface(ArrayMesh& Mesh, const Xeno::FMeshBuffers& Buffers)
		{
			const int64_t Count = static_cast<int64_t>(Buffers.Vertices());
			PackedVector2Array Positions;
			Positions.resize(Count);
			PackedColorArray Colors;
			Colors.resize(Count);
			PackedVector2Array Uvs;
			Uvs.resize(Count);
			PackedFloat32Array Look;
			Look.resize(Count * 4);
			for (int64_t Vertex = 0; Vertex < Count; ++Vertex)
			{
				const std::size_t At = static_cast<std::size_t>(Vertex);
				const float* P = &Buffers.Pos[At * 3];
				const float* C = &Buffers.Color[At * 4];
				const float* T = &Buffers.Uv[At * 2];
				const float* C0 = &Buffers.C0[At * 4];
				const float* C1 = &Buffers.C1[At * 4];
				Positions.set(Vertex, Vector2(P[0], P[1]));
				Colors.set(Vertex, Color(C[0], C[1], C[2], C[3]));
				Uvs.set(Vertex, Vector2(T[0], T[1]));
				Look.set(Vertex * 4 + 0, C0[0] + 1024.0f * C0[1]);
				Look.set(Vertex * 4 + 1, C1[0] + 1024.0f * C1[1]);
				Look.set(Vertex * 4 + 2, C0[2] + 8.0f * C0[3]);
				Look.set(Vertex * 4 + 3, C1[2]);
			}
			Array Arrays;
			Arrays.resize(Mesh::ARRAY_MAX);
			Arrays[Mesh::ARRAY_VERTEX] = Positions;
			Arrays[Mesh::ARRAY_COLOR] = Colors;
			Arrays[Mesh::ARRAY_TEX_UV] = Uvs;
			Arrays[Mesh::ARRAY_CUSTOM0] = Look;
			Arrays[Mesh::ARRAY_CUSTOM1] = Floats(Buffers.C2);
			const BitField<Mesh::ArrayFormat> Format = (Mesh::ARRAY_CUSTOM_RGBA_FLOAT << Mesh::ARRAY_FORMAT_CUSTOM0_SHIFT)
				| (Mesh::ARRAY_CUSTOM_RGBA_FLOAT << Mesh::ARRAY_FORMAT_CUSTOM1_SHIFT) | Mesh::ARRAY_FLAG_USE_2D_VERTICES;
			Mesh.add_surface_from_arrays(Mesh::PRIMITIVE_TRIANGLES, Arrays, Array(), Dictionary(), Format);
		}

		/** Vertices [First, End) of a mesh's buffers. */
		Xeno::FMeshBuffers Slice(const Xeno::FMeshBuffers& From, std::size_t First, std::size_t End)
		{
			Xeno::FMeshBuffers Out;
			const auto Copy = [&](const std::vector<float>& Source, std::vector<float>& Into, std::size_t Per) {
				if (Source.size() >= End * Per)
				{
					Into.assign(Source.begin() + static_cast<std::ptrdiff_t>(First * Per), Source.begin() + static_cast<std::ptrdiff_t>(End * Per));
				}
			};
			Copy(From.Pos, Out.Pos, 3);
			Copy(From.Normal, Out.Normal, 3);
			Copy(From.Color, Out.Color, 4);
			Copy(From.Uv, Out.Uv, 2);
			Copy(From.C0, Out.C0, 4);
			Copy(From.C1, Out.C1, 4);
			Copy(From.C2, Out.C2, 4);
			Copy(From.C3, Out.C3, 4);
			return Out;
		}

		/**
		 * The pieces a run of the 2D layer is drawn in. Weltall's renderer (Rendering/DrawListRendering.cpp, AddPasses)
		 * draws a textured semi-transparent primitive whose texels do not all blend on its own: its plain texels, then its
		 * blending ones. A canvas does both in one pass for average and the adds (premultiplied alpha), not for subtract:
		 * a subtracting run with such primitives is drawn a triangle at a time (a quad's two triangles never overlap, so
		 * this is a primitive at a time), each in two passes. Every other run is one piece.
		 */
		std::vector<std::pair<std::size_t, std::size_t>> FlatPieces(const Xeno::FSurface& Surface, bool bPictureMixed)
		{
			const std::size_t Vertices = Surface.Mesh.Vertices();
			bool bMixed = false;
			if (Surface.Blend == Xeno::EBlend::Subtract && Surface.Mesh.C0.size() >= Vertices * 4)
			{
				for (std::size_t Vertex = 0; Vertex < Vertices && !bMixed; ++Vertex)
				{
					const int Depth = static_cast<int>(Surface.Mesh.C0[Vertex * 4 + 2] + 0.5f);
					const int Flags = static_cast<int>(Surface.Mesh.C0[Vertex * 4 + 3] + 0.5f);
					// Untextured primitives and those whose every texel blends draw in one pass; a picture of the pack's
					// takes its texels' kinds from the original texels under it (FSession::TexelKinds), mixed or not.
					bMixed = (Surface.Texture.empty() || bPictureMixed) && Depth != 3 && (Flags & 4) == 0;
				}
			}
			std::vector<std::pair<std::size_t, std::size_t>> Pieces;
			if (!bMixed)
			{
				Pieces.emplace_back(0, Vertices);
				return Pieces;
			}
			for (std::size_t First = 0; First + 3 <= Vertices; First += 3)
			{
				Pieces.emplace_back(First, First + 3);
			}
			return Pieces;
		}

		Array FillMesh(const Ref<ArrayMesh>& Mesh, const std::vector<Xeno::FSurface>& Surfaces)
		{
			Array Made;
			ERR_FAIL_COND_V(Mesh.is_null(), Made);
			Mesh->clear_surfaces();
			for (const Xeno::FSurface& Surface : Surfaces)
			{
				if (Surface.Mesh.Vertices() == 0)
				{
					continue;
				}
				AddSurface(**Mesh, Surface.Mesh);
				Array Entry;
				Entry.push_back(static_cast<int>(Surface.Blend));
				Entry.push_back(ToGodot(Surface.Texture));
				Entry.push_back(Surface.Vram);
				Entry.push_back(Surface.bUnlit);
				Made.push_back(Entry);
			}
			return Made;
		}
	}

	XenoCore::XenoCore()
	{
		Session.SetPictureReader(ReadPicture);
	}

	Ref<Image> XenoCore::page_image(const String& key) const
	{
		int Size = 0;
		const std::vector<uint8_t> Rgba = Session.PageImage(key.utf8().get_data(), Size);
		PackedByteArray Data;
		Data.resize(static_cast<int64_t>(Rgba.size()));
		std::memcpy(Data.ptrw(), Rgba.data(), Rgba.size());
		return Image::create_from_data(Size, Size, false, Image::FORMAT_RGBA8, Data);
	}

	Ref<Image> XenoCore::texel_kinds(const String& key) const
	{
		int Width = 0, Height = 0;
		const std::vector<uint8_t> Kinds = Session.TexelKinds(key.utf8().get_data(), Width, Height);
		if (Kinds.empty())
		{
			return Ref<Image>();
		}
		PackedByteArray Data;
		Data.resize(static_cast<int64_t>(Kinds.size()));
		std::memcpy(Data.ptrw(), Kinds.data(), Kinds.size());
		return Image::create_from_data(Width, Height, false, Image::FORMAT_R8, Data);
	}

	String XenoCore::open(const String& games_folder, const String& translation_image)
	{
		return ToGodot(Session.Open(games_folder.utf8().get_data(), translation_image.utf8().get_data()));
	}

	String XenoCore::language() const
	{
		return ToGodot(Session.Language());
	}

	Dictionary XenoCore::survey_discs(const String& folder) const
	{
		const auto Text = [](const std::filesystem::path& Path) {
			const std::u8string Name = Path.u8string();
			return String::utf8(reinterpret_cast<const char*>(Name.c_str()));
		};
		const Xeno::FDiscSurvey Survey = Xeno::SurveyDiscs(std::filesystem::u8path(folder.utf8().get_data()));
		Dictionary Out;
		Out["usa_disc_1"] = Text(Survey.First(Xeno::EDiscKind::UsaDisc1));
		Out["usa_disc_2"] = Text(Survey.First(Xeno::EDiscKind::UsaDisc2));
		Out["russian_disc_1"] = Text(Survey.First(Xeno::EDiscKind::RussianDisc1));
		Out["russian_disc_2"] = Text(Survey.First(Xeno::EDiscKind::RussianDisc2));
		Array Others;
		for (const Xeno::FFoundDisc& Disc : Survey.Discs)
		{
			if (Disc.Kind == Xeno::EDiscKind::Other)
			{
				Array Entry;
				Entry.append(Text(Disc.File));
				Entry.append(ToGodot(Disc.Note));
				Others.append(Entry);
			}
		}
		Out["others"] = Others;
		return Out;
	}

	Array XenoCore::open_messages() const
	{
		Array Messages;
		for (const Xeno::FSession::FOpenMessage& Message : Session.OpenMessages())
		{
			Dictionary Entry;
			Entry["map"] = Message.Map;
			Entry["index"] = Message.Index;
			Entry["lines"] = Message.Lines;
			Entry["portrait"] = Message.bPortrait;
			PackedByteArray Codes;
			Codes.resize(static_cast<int64_t>(Message.Codes.size()));
			std::memcpy(Codes.ptrw(), Message.Codes.data(), Message.Codes.size());
			Entry["codes"] = Codes;
			Messages.push_back(Entry);
		}
		return Messages;
	}

	String XenoCore::set_pack(const String& folder)
	{
		return ToGodot(Session.SetPack(folder.utf8().get_data()));
	}

	int XenoCore::pack_pictures() const
	{
		return Session.PackPictures();
	}

	void XenoCore::set_options(bool hd, bool original_shadows, bool soft_shadows)
	{
		Session.SetOptions({hd, original_shadows, soft_shadows});
	}

	String XenoCore::enter_field(int map)
	{
		return ToGodot(Session.EnterField(map));
	}

	String XenoCore::set_alias_index(const String& path)
	{
		return ToGodot(Session.SetAliasIndex(path.utf8().get_data()));
	}

	String XenoCore::enter_field_keeping(int map)
	{
		return ToGodot(Session.EnterFieldKeeping(map));
	}

	String XenoCore::load_card(const String& path, int slot)
	{
		std::string Listing;
		const std::string Error = Session.LoadCard(path.utf8().get_data(), slot, Listing);
		return ToGodot(slot < 0 && Error.empty() ? Listing : Error);
	}

	String XenoCore::set_save_folder(const String& folder)
	{
		return ToGodot(Session.SetSaveFolder(folder.utf8().get_data()));
	}

	String XenoCore::save_state(const String& path)
	{
		return ToGodot(Session.SaveState(path.utf8().get_data()));
	}

	String XenoCore::load_state(const String& path)
	{
		return ToGodot(Session.LoadState(path.utf8().get_data()));
	}

	void XenoCore::set_rolling_state(int every)
	{
		Session.SetRollingState(every);
	}

	Dictionary XenoCore::rolling_stats() const
	{
		const Xeno::FRollingStats Stats = Session.RollingStats();
		Dictionary Out;
		Out["every"] = Stats.Every;
		Out["tries"] = Stats.Tries;
		Out["captures"] = Stats.Captures;
		Out["usec_total"] = Stats.UsecTotal;
		Out["usec_longest"] = Stats.UsecLongest;
		Out["failed_try_usec_longest"] = Stats.FailedTryUsecLongest;
		return Out;
	}

	Dictionary XenoCore::write_report_state(const String& path)
	{
		const Xeno::FReportState State = Session.WriteReportState(path.utf8().get_data());
		Dictionary Out;
		Out["source"] = ToGodot(State.Source);
		Out["error"] = ToGodot(State.Error);
		PackedInt32Array Inputs;
		Inputs.resize(static_cast<int64_t>(State.Inputs.size()));
		for (std::size_t Frame = 0; Frame < State.Inputs.size(); ++Frame)
		{
			Inputs.set(static_cast<int64_t>(Frame), State.Inputs[Frame]);
		}
		Out["inputs"] = Inputs;
		Out["vblanks"] = State.Vblanks;
		Out["turbo_frames"] = State.TurboFrames;
		Out["cheats"] = State.Cheats;
		Out["seconds"] = State.Seconds;
		return Out;
	}

	String XenoCore::frame_report()
	{
		return ToGodot(Session.FrameReport());
	}

	String XenoCore::step(int buttons, int stick_x, int stick_y, bool analog)
	{
		return ToGodot(Session.Step(static_cast<uint16_t>(buttons), static_cast<uint8_t>(stick_x), static_cast<uint8_t>(stick_y), analog));
	}

	int XenoCore::vblanks_per_frame() const
	{
		return Session.VblanksPerFrame();
	}

	double XenoCore::vblank_seconds() const
	{
		return Xeno::FSession::VblankSeconds();
	}

	int XenoCore::vblanks_due(double seconds)
	{
		return Session.VblanksDue(seconds);
	}

	Dictionary XenoCore::cheat_state() const
	{
		const Xeno::FCheatState State = Session.CheatState();
		Dictionary Out;
		Out["can_edit"] = State.bCanEdit;
		Out["in_battle"] = State.bInBattle;
		Out["can_win"] = State.bCanWin;
		Out["enemies_left"] = State.EnemiesLeft;
		Out["program"] = State.Program;
		Out["gold"] = static_cast<int64_t>(State.Gold);
		Out["encounters_off"] = State.bEncountersOff;
		Out["turbo"] = State.Turbo;
		Out["pace"] = Session.GamePace();
		Array Party;
		for (const Xeno::FCheatHero& Hero : State.Party)
		{
			Dictionary Entry;
			Entry["id"] = Hero.Character;
			Entry["name"] = ToGodot(Hero.Name);
			Entry["level"] = Hero.Level;
			Entry["ether_level"] = Hero.EtherLevel;
			Entry["exp"] = static_cast<int64_t>(Hero.Exp);
			Entry["ether_exp"] = static_cast<int64_t>(Hero.EtherExp);
			Entry["exp_next"] = static_cast<int64_t>(Hero.ExpToNext);
			Entry["ether_next"] = static_cast<int64_t>(Hero.EtherExpToNext);
			Entry["hp"] = Hero.Hp;
			Entry["max_hp"] = Hero.MaxHp;
			Entry["ep"] = Hero.Ep;
			Entry["max_ep"] = Hero.MaxEp;
			Entry["attack"] = Hero.Attack;
			Entry["defense"] = Hero.Defense;
			Entry["agility"] = Hero.Agility;
			Entry["ether"] = Hero.Ether;
			Entry["ether_defense"] = Hero.EtherDefense;
			Entry["hit"] = Hero.Hit;
			Entry["evade"] = Hero.Evade;
			Entry["gear"] = Hero.Gear;
			Entry["gear_name"] = ToGodot(Hero.GearName);
			Entry["gear_hp"] = Hero.GearHp;
			Entry["gear_max_hp"] = Hero.GearMaxHp;
			Entry["fuel"] = Hero.Fuel;
			Entry["max_fuel"] = Hero.MaxFuel;
			// The Deathblows: [number, name, learned, level asked, percent, 7-AP tier open, the presses that finish it].
			Array Deathblows;
			int Learned = 0;
			for (const Xeno::FCheatDeathblow& Deathblow : Hero.Deathblows)
			{
				Learned += Deathblow.bLearned ? 1 : 0;
				Array Row = Array::make(Deathblow.Number, ToGodot(Deathblow.Name), Deathblow.bLearned, Deathblow.Level, Deathblow.Percent, Deathblow.bTierOpen);
				Row.push_back(ToGodot(Deathblow.Buttons));
				Deathblows.push_back(Row);
			}
			Entry["deathblows"] = Deathblows;
			Entry["deathblows_learned"] = Learned;
			Entry["deathblows_total"] = static_cast<int>(Hero.Deathblows.size());
			Entry["gear_deathblows"] = Hero.GearDeathblows;
			Entry["ap"] = Hero.ApPerTurn;
			Party.push_back(Entry);
		}
		Out["party"] = Party;
		Array Items;
		for (const Xeno::FCheatItem& Item : State.Items)
		{
			Items.push_back(Array::make(Item.Id, ToGodot(Item.Name), Item.Count));
		}
		Out["items"] = Items;
		return Out;
	}

	Array XenoCore::cheat_items(int list) const
	{
		Array Out;
		for (const Xeno::FCheatItem& Item : Session.CheatItems(list, false))
		{
			Out.push_back(Array::make(Item.Id, ToGodot(Item.Name), Item.Count));
		}
		return Out;
	}

	String XenoCore::cheat(const String& command)
	{
		return ToGodot(Session.Cheat(command.utf8().get_data()));
	}

	String XenoCore::ask_battling(const PackedInt32Array& parameters)
	{
		std::array<int, 6> Bytes{};
		for (int64_t Byte = 0; Byte < parameters.size() && Byte < 6; ++Byte)
		{
			Bytes[static_cast<std::size_t>(Byte)] = parameters[Byte];
		}
		return ToGodot(Session.AskBattling(Bytes));
	}

	String XenoCore::ask_field_movie(int number, int end_frame)
	{
		return ToGodot(Session.AskFieldMovie(number, end_frame));
	}

	int XenoCore::game_pace() const
	{
		return Session.GamePace();
	}

	int XenoCore::program_runs() const
	{
		return Session.ProgramRuns();
	}

	int XenoCore::sound_rate() const
	{
		return Xeno::FSession::SoundRate();
	}

	int XenoCore::sound_lead_frames() const
	{
		return Xeno::FSession::SoundLeadFrames();
	}

	String XenoCore::hear(int latency_frames)
	{
		return ToGodot(Session.Hear(latency_frames));
	}

	PackedFloat32Array XenoCore::screen_wave() const
	{
		const std::vector<float> Cells = Session.ScreenWave();
		PackedFloat32Array Out;
		Out.resize(static_cast<int64_t>(Cells.size()));
		for (std::size_t Index = 0; Index < Cells.size(); ++Index)
		{
			Out.set(static_cast<int64_t>(Index), Cells[Index]);
		}
		return Out;
	}

	PackedVector2Array XenoCore::render_sound(int frames)
	{
		PackedVector2Array Out;
		if (frames <= 0)
		{
			return Out;
		}
		SoundScratch.resize(static_cast<std::size_t>(frames) * 2);
		if (!Session.RenderSound(SoundScratch.data(), frames))
		{
			return Out;
		}
		Out.resize(frames);
		Vector2* To = Out.ptrw();
		constexpr float Scale = 1.0f / 32768.0f;
		for (int Frame = 0; Frame < frames; ++Frame)
		{
			To[Frame] = Vector2(SoundScratch[static_cast<std::size_t>(Frame) * 2] * Scale, SoundScratch[static_cast<std::size_t>(Frame) * 2 + 1] * Scale);
		}
		return Out;
	}

	Dictionary XenoCore::info() const
	{
		const Xeno::FFrameInfo Info = Session.Info();
		Dictionary Out;
		Out["program"] = Info.Program;
		Out["map"] = Info.Map;
		Out["field"] = Info.bField;
		Out["running"] = Info.bRunning;
		Out["scene_drawn"] = Info.bSceneDrawn;
		Out["tick"] = Info.Tick;
		Out["leader"] = Info.Leader;
		Out["leader_position"] = Vector3i(Info.LeaderPosition[0], Info.LeaderPosition[1], Info.LeaderPosition[2]);
		Out["leader_frame"] = Info.LeaderFrame;
		Out["message_open"] = Info.bMessageOpen;
		Out["characters"] = Info.Characters;
		Out["background"] = Color(Info.Background[0] / 255.0f, Info.Background[1] / 255.0f, Info.Background[2] / 255.0f);
		Out["projection_distance"] = Info.ProjectionDistance;
		Out["hd_upload"] = Info.HdUpload;
		Out["hd_rect"] = Info.HdRect;
		Out["hd_split"] = Info.HdSplit;
		Out["from_vram"] = Info.FromVram;
		Out["map_loads"] = Info.MapLoads;
		// The sweep's tallies of the last frame built: sprite pieces and 2D primitives wholly from the pack or not.
		Out["sprite_pieces"] = Info.SpritePieces;
		Out["sprite_hd"] = Info.SpriteHd;
		Out["sprite_partial"] = Info.SpritePartial;
		Out["sprite_vram"] = Info.SpriteVram;
		Out["screen_textured"] = Info.ScreenTextured;
		Out["screen_hd"] = Info.ScreenHd;
		Out["sprite_waiting"] = Info.SpriteWaiting;
		Out["screen_waiting"] = Info.ScreenWaiting;
		Out["scenery_hd"] = Info.SceneryHd;
		Out["scenery_laid"] = Info.SceneryLaid;
		Out["scenery_vram"] = Info.SceneryVram;
		// The battle: drawn as the PS1 draws it (unlit: no sun, no SSAO, no soft shadows), in its frame's drawing order.
		Out["battle"] = Info.bBattle;
		Out["unlit"] = Info.bUnlit;
		Out["screen_size"] = Vector2i(Info.ScreenWidth, Info.ScreenHeight);
		Out["battle_step"] = Info.BattleStep;
		Out["hud_primitives"] = Info.HudPrimitives;
		Out["hud_hash"] = static_cast<int64_t>(Info.HudHash);
		Out["scene_links"] = Info.SceneLinks;
		Out["over_links"] = Info.OverLinks;
		// The screens beside the field and the battle: the loop's stage, what shows (xeno_session.h EScreenKind), the menu,
		// the movie, the field's picture of the screen, a chapter's card, the 2D layer built last.
		Out["stage"] = Info.Stage;
		Out["screen"] = static_cast<int>(Info.Screen);
		Out["menu_mode"] = Info.MenuMode;
		Out["menu_number"] = static_cast<int64_t>(Info.MenuNumber);
		Out["menu_primitives"] = Info.MenuPrimitives;
		Out["screen_primitives"] = Info.ScreenPrimitives;
		Out["screen_hash"] = static_cast<int64_t>(Info.ScreenHash);
		Out["movie_picture"] = Info.MoviePicture;
		Out["movie_frame"] = Info.MovieFrame;
		Out["movie_size"] = Vector2i(Info.MovieWidth, Info.MovieHeight);
		Out["movie_view"] = Info.MovieView;
		Out["movie_disc"] = Info.MovieDisc;
		Out["movie_number"] = Info.MovieNumber;
		Out["movie_shown_frame"] = Info.MovieShownFrame;
		Out["movie_source"] = String::utf8(Info.MovieSource.c_str());
		// The disc in the drive, and one the game waits on that the bridge has not found (the display says where to put it).
		Out["drive_disc"] = Info.DriveDisc;
		Out["drive_disc_id"] = String::utf8(Info.DriveDiscId.c_str());
		Out["drive_disc_file"] = String::utf8(Info.DriveDiscFile.c_str());
		Out["disc_wanted"] = Info.DiscWanted;
		Out["disc_wanted_kind"] = String::utf8(Info.DiscWantedKind.c_str());
		Out["disc_wanted_folder"] = String::utf8(Info.DiscWantedFolder.c_str());
		Out["discs_held"] = Info.DiscsHeld;
		Out["cover"] = Info.bCover;
		Out["cover_screen"] = Info.bCoverScreen;
		Out["cover_taken"] = Info.CoverTaken;
		Out["screen_in_vram"] = Info.ScreenInVram;
		Out["card_level"] = Info.CardLevel;
		Out["player_controlled"] = Info.bPlayerControlled;
		Out["menu_locked"] = Info.bMenuLocked;
		Out["waiting"] = Info.Waiting;
		Out["scene_lines"] = Info.SceneLines;
		Out["world_map"] = Info.bWorldMap;
		Out["world_scene"] = Info.WorldScene;
		Out["travel_mode"] = Info.TravelMode;
		Out["map_place"] = Info.MapPlace;
		Out["camera_yaw"] = Info.CameraYaw;
		Out["map_polygons"] = Info.MapPolygons;
		Out["one_sided_dropped"] = Info.MapOneSidedDropped;
		Out["map_animated"] = Vector2i(Info.MapAnimatedPieces, Info.MapAnimatedHd);
		PackedInt32Array Layers;
		for (const int Count : Info.MapLayers)
		{
			Layers.push_back(Count);
		}
		Out["map_layers"] = Layers;
		Out["fade_level"] = Info.FadeLevel;
		// The Battling arena: its stage (0 menus, 1 versus, 2 bout), the fight's state, round, last round's winner, the bout's
		// result; each side's gear, HP of its maximum and place; the frame's columns, its pause's blurs, the demonstration's trails.
		Out["battling"] = Info.bBattling;
		Out["arena_stage"] = Info.ArenaStage;
		Out["arena_state"] = Info.ArenaState;
		Out["arena_round"] = Info.ArenaRound;
		Out["arena_winner"] = Info.ArenaWinner;
		Out["arena_result"] = Info.ArenaResult;
		Out["arena_gears"] = Vector2i(Info.ArenaGears[0], Info.ArenaGears[1]);
		Out["arena_hp"] = Vector2i(Info.ArenaHp[0], Info.ArenaHp[1]);
		Out["arena_max_hp"] = Vector2i(Info.ArenaMaxHp[0], Info.ArenaMaxHp[1]);
		Out["arena_position_0"] = Vector3i(Info.ArenaPositions[0][0], Info.ArenaPositions[0][1], Info.ArenaPositions[0][2]);
		Out["arena_position_1"] = Vector3i(Info.ArenaPositions[1][0], Info.ArenaPositions[1][1], Info.ArenaPositions[1][2]);
		Out["arena_columns"] = Info.ArenaColumns;
		Out["arena_blurs"] = Info.ArenaBlurs;
		Out["arena_trails"] = Info.bArenaTrails;
		return Out;
	}

	PackedByteArray XenoCore::vram() const
	{
		PackedByteArray Out;
		const uint16_t* Units = Session.Vram();
		const int64_t Bytes = 1024LL * Session.VramRows() * 2;
		Out.resize(Bytes);
		if (Units != nullptr)
		{
			std::memcpy(Out.ptrw(), Units, static_cast<std::size_t>(Bytes));
		}
		else
		{
			Out.fill(0);
		}
		return Out;
	}

	int XenoCore::vram_rows() const
	{
		return Session.VramRows();
	}

	Array XenoCore::fill_world(const Ref<ArrayMesh>& mesh)
	{
		Session.BuildWorld(World);
		return FillMesh(mesh, World);
	}

	Array XenoCore::fill_screen(const Ref<ArrayMesh>& mesh)
	{
		Session.BuildScreen(Screen);
		return FillMesh(mesh, Screen);
	}

	Array XenoCore::fill_flat(const Array& meshes)
	{
		Session.BuildScreen(Screen);
		Array Made;
		Array Meshes = meshes;
		int64_t Next = 0;
		for (const Xeno::FSurface& Surface : Screen)
		{
			if (Surface.Mesh.Vertices() == 0)
			{
				continue;
			}
			const std::vector<std::pair<std::size_t, std::size_t>> Pieces = FlatPieces(Surface, !Surface.Texture.empty() && Session.TexelKindsMixed(Surface.Texture));
			for (const auto& [First, End] : Pieces)
			{
				if (Next >= Meshes.size())
				{
					Ref<ArrayMesh> Grown;
					Grown.instantiate();
					Meshes.push_back(Grown);
				}
				Ref<ArrayMesh> Mesh = Meshes[Next];
				Mesh->clear_surfaces();
				AddFlatSurface(**Mesh, Pieces.size() == 1 ? Surface.Mesh : Slice(Surface.Mesh, First, End));
				++Next;
				Array Entry;
				Entry.push_back(static_cast<int>(Surface.Blend));
				Entry.push_back(ToGodot(Surface.Texture));
				Entry.push_back(Surface.Vram);
				Entry.push_back(Surface.bUnlit);
				Entry.push_back(Vector4(Surface.Area[0], Surface.Area[1], Surface.Area[2], Surface.Area[3]));
				// Whether the piece's texels may not all blend (a subtracting piece then takes two passes).
				Entry.push_back(Pieces.size() > 1);
				Made.push_back(Entry);
			}
		}
		return Made;
	}

	Transform3D XenoCore::view_transform() const
	{
		const std::array<float, 12> M = Session.ViewTransform();
		const Basis Rows(M[0], M[1], M[2], M[3], M[4], M[5], M[6], M[7], M[8]);
		return Transform3D(Rows, Vector3(M[9], M[10], M[11]));
	}

	String XenoCore::power_on()
	{
		return ToGodot(Session.PowerOn());
	}

	PackedByteArray XenoCore::vram_of(int source)
	{
		PackedByteArray Out;
		const uint16_t* Units = Session.VramOf(source);
		if (Units == nullptr)
		{
			return Out;
		}
		const int64_t Bytes = 1024LL * Session.VramRows() * 2;
		Out.resize(Bytes);
		std::memcpy(Out.ptrw(), Units, static_cast<std::size_t>(Bytes));
		return Out;
	}

	int64_t XenoCore::vram_stamp(int source) const
	{
		return static_cast<int64_t>(Session.VramStamp(source));
	}

	Ref<Image> XenoCore::movie_image() const
	{
		std::vector<uint8_t> Rgba;
		int Width = 0, Height = 0;
		if (!Session.MovieImage(Rgba, Width, Height))
		{
			return Ref<Image>();
		}
		PackedByteArray Data;
		Data.resize(static_cast<int64_t>(Rgba.size()));
		std::memcpy(Data.ptrw(), Rgba.data(), Rgba.size());
		return Image::create_from_data(Width, Height, false, Image::FORMAT_RGBA8, Data);
	}

	Ref<Image> XenoCore::take_screen_picture(const Ref<Image>& image, int taken)
	{
		ERR_FAIL_COND_V(image.is_null(), Ref<Image>());
		Ref<Image> Picture = image->duplicate();
		Picture->convert(Image::FORMAT_RGBA8);
		PackedByteArray Data = Picture->get_data();
		const int Width = Picture->get_width(), Height = Picture->get_height();
		Session.SetScreenPicture(taken, Data.ptr(), Width, Height);
		// Opaque, its black pixels let through: as the PS1 skips a texel of 0.
		uint8_t* Pixels = Data.ptrw();
		for (int64_t Pixel = 0; Pixel < static_cast<int64_t>(Width) * Height; ++Pixel)
		{
			uint8_t* At = Pixels + Pixel * 4;
			At[3] = (At[0] >> 3 | At[1] >> 3 | At[2] >> 3) != 0 ? 255 : 0;
		}
		return Image::create_from_data(Width, Height, false, Image::FORMAT_RGBA8, Data);
	}

	void XenoCore::set_lazy_textures(bool lazy)
	{
		Session.SetLazyTextures(lazy);
	}

	void XenoCore::mark_texture_ready(const String& key)
	{
		Session.MarkTextureReady(key.utf8().get_data());
	}

	PackedStringArray XenoCore::wanted_textures()
	{
		PackedStringArray Out;
		for (const std::string& Key : Session.TakeWantedTextures())
		{
			Out.push_back(ToGodot(Key));
		}
		return Out;
	}

	int XenoCore::texture_job(const String& key)
	{
		FJob Job;
		const std::string Key = key.utf8().get_data();
		Job.bPage = Key.rfind("page:", 0) == 0;
		Job.Path = Key;
		if (Job.bPage)
		{
			// What the page needs from VRAM and the pack is taken now, on the game's thread; the rest needs nothing of the game.
			Job.Page = Session.PageJob(Key);
		}
		const std::lock_guard<std::mutex> Lock(JobLock);
		const int Id = NextJob++;
		Jobs.emplace(Id, std::move(Job));
		return Id;
	}

	void XenoCore::build_job(int job)
	{
		FJob Job;
		{
			const std::lock_guard<std::mutex> Lock(JobLock);
			const auto Found = Jobs.find(job);
			if (Found == Jobs.end())
			{
				return;
			}
			Job = std::move(Found->second);
			Jobs.erase(Found);
		}
		Ref<Image> Made;
		if (Job.bPage)
		{
			int Size = 0;
			const std::vector<uint8_t> Rgba = Xeno::FSession::BuildPage(Job.Page, ReadPicture, Size);
			PackedByteArray Data;
			Data.resize(static_cast<int64_t>(Rgba.size()));
			std::memcpy(Data.ptrw(), Rgba.data(), Rgba.size());
			Made = Image::create_from_data(Size, Size, false, Image::FORMAT_RGBA8, Data);
			Made->generate_mipmaps();
		}
		else
		{
			const PackedByteArray Bytes = FileAccess::get_file_as_bytes(String::utf8(Job.Path.c_str()));
			if (Bytes.size() >= 32 && Bytes[0] == 'X' && Bytes[1] == 'B' && Bytes[2] == 'C' && Bytes[3] == '7')
			{
				// A pack picture (XBC7: 32-byte header + zlib of BC7 levels) straight into a compressed texture, level 0.
				const int Width = static_cast<int>(Bytes.decode_u32(8)), Height = static_cast<int>(Bytes.decode_u32(12));
				PackedByteArray Raw = Bytes.slice(32);
				if (Bytes.decode_u32(28) & 1)
				{
					Raw = Raw.decompress(Bytes.decode_u32(24), FileAccess::COMPRESSION_DEFLATE);
				}
				const int64_t Level = static_cast<int64_t>((Width + 3) / 4) * ((Height + 3) / 4) * 16;
				if (Raw.size() >= Level)
				{
					Made = Image::create_from_data(Width, Height, false, Image::FORMAT_BPTC_RGBA, Raw.slice(0, Level));
				}
			}
			else if (!Bytes.is_empty())
			{
				Made.instantiate();
				if (Made->load_png_from_buffer(Bytes) != OK)
				{
					Made = Ref<Image>();
				}
			}
		}
		if (Made.is_null())
		{
			// Nothing could be read: an empty picture says so (the display draws VRAM's texels on).
			Made = Image::create_empty(1, 1, false, Image::FORMAT_RGBA8);
			Made->set_meta("failed", true);
		}
		const std::lock_guard<std::mutex> Lock(JobLock);
		Built[job] = Made;
	}

	Ref<Image> XenoCore::take_built(int job)
	{
		const std::lock_guard<std::mutex> Lock(JobLock);
		const auto Found = Built.find(job);
		if (Found == Built.end())
		{
			return Ref<Image>();
		}
		Ref<Image> Made = Found->second;
		Built.erase(Found);
		return Made;
	}

	void XenoCore::_bind_methods()
	{
		ClassDB::bind_method(D_METHOD("power_on"), &XenoCore::power_on);
		ClassDB::bind_method(D_METHOD("vram_of", "source"), &XenoCore::vram_of);
		ClassDB::bind_method(D_METHOD("vram_stamp", "source"), &XenoCore::vram_stamp);
		ClassDB::bind_method(D_METHOD("movie_image"), &XenoCore::movie_image);
		ClassDB::bind_method(D_METHOD("take_screen_picture", "image", "taken"), &XenoCore::take_screen_picture);
		ClassDB::bind_method(D_METHOD("set_lazy_textures", "lazy"), &XenoCore::set_lazy_textures);
		ClassDB::bind_method(D_METHOD("mark_texture_ready", "key"), &XenoCore::mark_texture_ready);
		ClassDB::bind_method(D_METHOD("wanted_textures"), &XenoCore::wanted_textures);
		ClassDB::bind_method(D_METHOD("texture_job", "key"), &XenoCore::texture_job);
		ClassDB::bind_method(D_METHOD("build_job", "job"), &XenoCore::build_job);
		ClassDB::bind_method(D_METHOD("take_built", "job"), &XenoCore::take_built);
		ClassDB::bind_method(D_METHOD("open", "games_folder", "translation_image"), &XenoCore::open, DEFVAL(String()));
		ClassDB::bind_method(D_METHOD("language"), &XenoCore::language);
		ClassDB::bind_method(D_METHOD("survey_discs", "folder"), &XenoCore::survey_discs);
		ClassDB::bind_method(D_METHOD("open_messages"), &XenoCore::open_messages);
		ClassDB::bind_method(D_METHOD("set_pack", "folder"), &XenoCore::set_pack);
		ClassDB::bind_method(D_METHOD("pack_pictures"), &XenoCore::pack_pictures);
		ClassDB::bind_method(D_METHOD("set_options", "hd", "original_shadows", "soft_shadows"), &XenoCore::set_options);
		ClassDB::bind_method(D_METHOD("page_image", "key"), &XenoCore::page_image);
		ClassDB::bind_method(D_METHOD("texel_kinds", "key"), &XenoCore::texel_kinds);
		ClassDB::bind_method(D_METHOD("enter_field", "map"), &XenoCore::enter_field);
		ClassDB::bind_method(D_METHOD("enter_field_keeping", "map"), &XenoCore::enter_field_keeping);
		ClassDB::bind_method(D_METHOD("set_alias_index", "path"), &XenoCore::set_alias_index);
		ClassDB::bind_method(D_METHOD("load_card", "path", "slot"), &XenoCore::load_card);
		ClassDB::bind_method(D_METHOD("set_save_folder", "folder"), &XenoCore::set_save_folder);
		ClassDB::bind_method(D_METHOD("save_state", "path"), &XenoCore::save_state);
		ClassDB::bind_method(D_METHOD("load_state", "path"), &XenoCore::load_state);
		ClassDB::bind_method(D_METHOD("set_rolling_state", "every"), &XenoCore::set_rolling_state);
		ClassDB::bind_method(D_METHOD("rolling_stats"), &XenoCore::rolling_stats);
		ClassDB::bind_method(D_METHOD("write_report_state", "path"), &XenoCore::write_report_state);
		ClassDB::bind_method(D_METHOD("frame_report"), &XenoCore::frame_report);
		ClassDB::bind_method(D_METHOD("step", "buttons", "stick_x", "stick_y", "analog"), &XenoCore::step);
		ClassDB::bind_method(D_METHOD("vblanks_per_frame"), &XenoCore::vblanks_per_frame);
		ClassDB::bind_method(D_METHOD("vblank_seconds"), &XenoCore::vblank_seconds);
		ClassDB::bind_method(D_METHOD("vblanks_due", "seconds"), &XenoCore::vblanks_due);
		ClassDB::bind_method(D_METHOD("sound_rate"), &XenoCore::sound_rate);
		ClassDB::bind_method(D_METHOD("sound_lead_frames"), &XenoCore::sound_lead_frames);
		ClassDB::bind_method(D_METHOD("hear", "latency_frames"), &XenoCore::hear);
		ClassDB::bind_method(D_METHOD("render_sound", "frames"), &XenoCore::render_sound);
		ClassDB::bind_method(D_METHOD("screen_wave"), &XenoCore::screen_wave);
		ClassDB::bind_method(D_METHOD("info"), &XenoCore::info);
		ClassDB::bind_method(D_METHOD("vram"), &XenoCore::vram);
		ClassDB::bind_method(D_METHOD("vram_rows"), &XenoCore::vram_rows);
		ClassDB::bind_method(D_METHOD("fill_world", "mesh"), &XenoCore::fill_world);
		ClassDB::bind_method(D_METHOD("fill_screen", "mesh"), &XenoCore::fill_screen);
		ClassDB::bind_method(D_METHOD("fill_flat", "meshes"), &XenoCore::fill_flat);
		ClassDB::bind_method(D_METHOD("view_transform"), &XenoCore::view_transform);
		ClassDB::bind_method(D_METHOD("cheat_state"), &XenoCore::cheat_state);
		ClassDB::bind_method(D_METHOD("cheat_items", "list"), &XenoCore::cheat_items);
		ClassDB::bind_method(D_METHOD("cheat", "command"), &XenoCore::cheat);
		ClassDB::bind_method(D_METHOD("ask_battling", "parameters"), &XenoCore::ask_battling);
		ClassDB::bind_method(D_METHOD("ask_field_movie", "number", "end_frame"), &XenoCore::ask_field_movie);
		ClassDB::bind_method(D_METHOD("game_pace"), &XenoCore::game_pace);
		ClassDB::bind_method(D_METHOD("program_runs"), &XenoCore::program_runs);
	}
}
